from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..adapters import AIClient

__all__ = [
    "AIInvokeConfig",
    "PipelineError",
    "PromptDefinitionData",
    "SegmentInput",
    "SegmentProcessingResult",
    "SegmentRetryResult",
    "SegmentSummary",
    "invoke_ai_response",
    "process_segments",
    "retry_segment",
]

REPORTS_DIR_NAME = "reports"
SEGMENTS_DIR_NAME = "segments"
METADATA_FILENAME = "metadata.json"
REPORT_FILENAME = "report.md"
FINAL_REPORT_FILENAME = "final_report.md"


@dataclass
class PromptDefinitionData:
    text: str
    priority: int = 0


@dataclass
class AIInvokeConfig:
    provider: str
    model: str
    system_prompts: List[PromptDefinitionData] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_metadata(cls, payload: Dict[str, Any]) -> "AIInvokeConfig":
        prompts_payload = payload.get("system_prompts", [])
        system_prompts = [
            PromptDefinitionData(
                text=str(item.get("text", "")),
                priority=int(item.get("priority", 0)),
            )
            for item in prompts_payload
            if item.get("text")
        ]
        options = payload.get("options", {})
        if not isinstance(options, dict):
            options = {}
        return cls(
            provider=str(payload.get("provider", "")).strip(),
            model=str(payload.get("model", "")).strip(),
            system_prompts=system_prompts,
            options=options,
        )

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "system_prompts": [
                {"text": prompt.text, "priority": prompt.priority}
                for prompt in self.system_prompts
            ],
            "options": self.options,
        }

    def prompt_definitions(self) -> List[tuple[str, int]]:
        return [(prompt.text, prompt.priority) for prompt in self.system_prompts]


@dataclass
class SegmentInput:
    index: int
    text: str
    start_offset: int
    end_offset: int
    byte_length: int
    character_count: int


@dataclass
class SegmentSummary:
    index: int
    start_offset: int
    end_offset: int
    byte_length: int
    character_count: int
    markdown_path: Path


@dataclass
class SegmentProcessingResult:
    report_name: str
    report_dir: Path
    metadata_path: Path
    segments: List[SegmentSummary]
    report_path: Optional[Path]
    final_report_path: Optional[Path]


@dataclass
class SegmentRetryResult:
    report_name: str
    report_dir: Path
    metadata_path: Path
    segment: SegmentSummary
    report_path: Optional[Path]
    final_report_path: Optional[Path]


class PipelineError(RuntimeError):
    """Raised when pipeline operations fail."""


def sanitize_report_name(candidate: Optional[str], fallback: str) -> str:
    base = (candidate or "").strip() or fallback.strip()
    if not base:
        base = "report"
    sanitized = re.sub(r"[^\w\-]+", "_", base, flags=re.UNICODE)
    sanitized = sanitized.strip("_")
    return sanitized or "report"


def invoke_ai_response(
    *,
    ai_config: AIInvokeConfig,
    segment_text: str,
    segment_index: int,
) -> str:
    client = AIClient(
        provider=ai_config.provider,
        model=ai_config.model,
        system_prompts=ai_config.prompt_definitions(),
    )
    payload = client.generate([segment_text], **ai_config.options)
    return _coerce_payload_to_text(payload)


def process_segments(
    *,
    project_dir: Path,
    source_filename: str,
    encoding: str,
    strategy: str,
    segments: Sequence[SegmentInput],
    ai_config: AIInvokeConfig,
    report_name: Optional[str] = None,
    cascade_integrate: bool = True,
    final_merge: bool = True,
) -> SegmentProcessingResult:
    if not project_dir.exists():
        raise PipelineError(f"Project directory does not exist: {project_dir}")

    fallback_name = Path(source_filename).stem or "report"
    sanitized_name = sanitize_report_name(report_name, fallback_name)
    report_dir = _ensure_report_directory(project_dir, sanitized_name)
    segments_dir = report_dir / SEGMENTS_DIR_NAME

    if segments_dir.exists():
        shutil.rmtree(segments_dir)
    segments_dir.mkdir(parents=True, exist_ok=True)

    now = _now_iso()

    metadata = {
        "filename": source_filename,
        "encoding": encoding,
        "strategy": strategy,
        "report_name": sanitized_name,
        "created_at": now,
        "updated_at": now,
        "segments": [],
        "ai": ai_config.to_metadata(),
    }

    summaries: List[SegmentSummary] = []

    for segment in segments:
        markdown_filename = _segment_filename(segment.index)
        markdown_path = segments_dir / markdown_filename
        ai_output = invoke_ai_response(
            ai_config=ai_config,
            segment_text=segment.text,
            segment_index=segment.index,
        )
        content = _render_segment_markdown(segment, ai_output)
        markdown_path.write_text(content, encoding="utf-8")

        entry = {
            "index": segment.index,
            "start_offset": segment.start_offset,
            "end_offset": segment.end_offset,
            "byte_length": segment.byte_length,
            "character_count": segment.character_count,
            "markdown": str(markdown_path.relative_to(report_dir)),
            "updated_at": now,
        }
        metadata["segments"].append(entry)

        summaries.append(
            SegmentSummary(
                index=segment.index,
                start_offset=segment.start_offset,
                end_offset=segment.end_offset,
                byte_length=segment.byte_length,
                character_count=segment.character_count,
                markdown_path=markdown_path,
            )
        )

    metadata_path = _metadata_path(report_dir)
    _save_metadata(metadata_path, metadata)

    report_path: Optional[Path] = None
    final_report_path: Optional[Path] = None

    if cascade_integrate:
        report_path = _assemble_report(report_dir, metadata)

    if final_merge:
        if report_path is None:
            report_path = _assemble_report(report_dir, metadata)
        final_report_path = _assemble_final_report(report_dir, report_path, metadata)

    return SegmentProcessingResult(
        report_name=sanitized_name,
        report_dir=report_dir,
        metadata_path=metadata_path,
        segments=summaries,
        report_path=report_path,
        final_report_path=final_report_path,
    )


def retry_segment(
    *,
    project_dir: Path,
    report_name: str,
    segment_index: int,
    encoding_override: Optional[str] = None,
    ai_config: Optional[AIInvokeConfig] = None,
    cascade_integrate: bool = True,
    final_merge: bool = True,
) -> SegmentRetryResult:
    sanitized_name = sanitize_report_name(report_name, report_name)
    report_dir = project_dir / REPORTS_DIR_NAME / sanitized_name
    if not report_dir.exists():
        raise PipelineError(f"Report directory not found: {sanitized_name}")

    metadata_path = _metadata_path(report_dir)
    metadata = _load_metadata(metadata_path)

    if not metadata:
        raise PipelineError("Report metadata is missing")

    ai_metadata = metadata.get("ai", {})
    current_config = AIInvokeConfig.from_metadata(ai_metadata)

    if ai_config is None:
        ai_config = current_config
    else:
        metadata["ai"] = ai_config.to_metadata()
        current_config = ai_config

    segments_entries = metadata.get("segments", [])
    segment_entry = _find_segment_entry(segments_entries, segment_index)

    source_filename = metadata.get("filename")
    if not source_filename:
        raise PipelineError("Metadata does not include source filename")

    source_path = project_dir / source_filename
    if not source_path.exists():
        raise PipelineError(f"Source file missing: {source_filename}")

    encoding = encoding_override or metadata.get("encoding", "utf-8")
    try:
        text = source_path.read_text(encoding=encoding)
    except UnicodeDecodeError as exc:
        raise PipelineError(f"Failed to decode source file: {exc}") from exc

    start_offset = int(segment_entry.get("start_offset", 0))
    end_offset = int(segment_entry.get("end_offset", start_offset))
    if start_offset < 0 or end_offset < start_offset:
        raise PipelineError("Invalid segment offsets in metadata")

    segment_text = text[start_offset:end_offset]
    byte_length = len(segment_text.encode(encoding))
    character_count = len(segment_text)

    ai_output = invoke_ai_response(
        ai_config=current_config,
        segment_text=segment_text,
        segment_index=segment_index,
    )

    markdown_rel = segment_entry.get("markdown")
    if not isinstance(markdown_rel, str):
        raise PipelineError("Segment metadata missing markdown path")

    resolved_report_dir = report_dir.resolve()
    markdown_path = (resolved_report_dir / markdown_rel).resolve()
    if not markdown_path.is_relative_to(resolved_report_dir):
        raise PipelineError("Segment markdown path escapes report directory")

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    content = _render_segment_markdown(
        SegmentInput(
            index=segment_index,
            text=segment_text,
            start_offset=start_offset,
            end_offset=end_offset,
            byte_length=byte_length,
            character_count=character_count,
        ),
        ai_output,
    )
    markdown_path.write_text(content, encoding="utf-8")

    now = _now_iso()
    segment_entry.update(
        {
            "start_offset": start_offset,
            "end_offset": end_offset,
            "byte_length": byte_length,
            "character_count": character_count,
            "updated_at": now,
        }
    )
    metadata["updated_at"] = now

    _save_metadata(metadata_path, metadata)

    report_path: Optional[Path] = None
    final_report_path: Optional[Path] = None

    if cascade_integrate:
        report_path = _assemble_report(report_dir, metadata)

    if final_merge:
        if report_path is None:
            report_path = _assemble_report(report_dir, metadata)
        final_report_path = _assemble_final_report(report_dir, report_path, metadata)

    summary = SegmentSummary(
        index=segment_index,
        start_offset=start_offset,
        end_offset=end_offset,
        byte_length=byte_length,
        character_count=character_count,
        markdown_path=markdown_path,
    )

    return SegmentRetryResult(
        report_name=sanitized_name,
        report_dir=report_dir,
        metadata_path=metadata_path,
        segment=summary,
        report_path=report_path,
        final_report_path=final_report_path,
    )


def _ensure_report_directory(project_dir: Path, report_name: str) -> Path:
    report_dir = project_dir / REPORTS_DIR_NAME / report_name
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def _metadata_path(report_dir: Path) -> Path:
    return report_dir / METADATA_FILENAME


def _segment_filename(index: int) -> str:
    return f"segment_{index:04d}.md"


def _render_segment_markdown(segment: SegmentInput, ai_output: str) -> str:
    header = [
        f"## Segment {segment.index}",
        "",
        f"- Character count: {segment.character_count}",
        f"- Byte length: {segment.byte_length}",
        f"- Range: {segment.start_offset} - {segment.end_offset}",
        "",
        "### AI Response",
        "",
        ai_output.strip(),
        "",
        "### Original Segment",
        "",
        "```text",
        segment.text,
        "```",
        "",
    ]
    return "\n".join(header)


def _save_metadata(path: Path, metadata: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_metadata(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise PipelineError(f"Metadata file missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError("Failed to parse metadata file") from exc


def _assemble_report(report_dir: Path, metadata: Dict[str, Any]) -> Path:
    lines: List[str] = [f"# Report for {metadata.get('filename', 'unknown')}\n"]

    for entry in sorted(metadata.get("segments", []), key=lambda item: item.get("index", 0)):
        markdown_rel = entry.get("markdown")
        if not isinstance(markdown_rel, str):
            continue
        markdown_path = report_dir / markdown_rel
        if not markdown_path.exists():
            continue
        segment_content = markdown_path.read_text(encoding="utf-8").strip()
        if segment_content:
            lines.append(segment_content)

    report_path = report_dir / REPORT_FILENAME
    report_path.write_text("\n\n".join(lines).strip() + "\n", encoding="utf-8")
    return report_path


def _assemble_final_report(
    report_dir: Path,
    report_path: Path,
    metadata: Dict[str, Any],
) -> Path:
    header = [
        "# Final Report",
        "",
        f"- Source file: {metadata.get('filename', 'unknown')}",
        f"- Segment count: {len(metadata.get('segments', []))}",
        f"- Last updated: {metadata.get('updated_at', _now_iso())}",
        "",
    ]
    report_content = report_path.read_text(encoding="utf-8")
    final_path = report_dir / FINAL_REPORT_FILENAME
    final_path.write_text("\n".join(header) + report_content, encoding="utf-8")
    return final_path


def _coerce_payload_to_text(payload: Any) -> str:
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, Iterable):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if isinstance(message, dict) and "content" in message:
                    return str(message["content"])
                if "content" in choice:
                    return str(choice["content"])
        content = payload.get("content")
        if isinstance(content, str):
            return content
        output = payload.get("output") or payload.get("text")
        if isinstance(output, str):
            return output
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(payload)


def _find_segment_entry(segments: Sequence[Dict[str, Any]], index: int) -> Dict[str, Any]:
    for entry in segments:
        if int(entry.get("index", 0)) == index:
            return entry
    raise PipelineError(f"Segment index {index} not found in metadata")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
