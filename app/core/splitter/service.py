"""High level orchestrator for text splitting operations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from pydantic import ValidationError

from ..settings import Settings
from .exceptions import (
    InvalidStrategyError,
    ProjectPathError,
    SplitExecutionError,
    StrategyConfigurationError,
)
from .strategies import (
    CharacterCountSplitter,
    ChapterKeywordSplitter,
    FixedCountSplitter,
    RatioSplitter,
    SplitSegment,
    TextSplitter,
)
from .types import (
    SplitStrategyType,
    StrategyParameter,
    parse_strategy_parameters,
)


_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(slots=True)
class SegmentStats:
    """Computed statistics for a split segment."""

    index: int
    start_offset: int
    end_offset: int
    byte_start_offset: int
    byte_end_offset: int
    character_count: int
    byte_count: int
    text: str

    @property
    def filename(self) -> str:
        return f"{self.index}.txt"


@dataclass(slots=True)
class SplitPreviewResult:
    """Aggregate preview results."""

    project_id: str
    strategy: SplitStrategyType
    parameters: Dict[str, Any]
    segments: List[SegmentStats]
    total_characters: int
    total_bytes: int
    source_sha256: str


@dataclass(slots=True)
class SplitExecutionResult:
    """Result of executing a split operation producing files."""

    preview: SplitPreviewResult
    output_directory: Path
    metadata_path: Path
    written_files: List[str]


_STRATEGY_BUILDERS: Mapping[SplitStrategyType, type[TextSplitter]] = {
    SplitStrategyType.CHARACTER_COUNT: CharacterCountSplitter,
    SplitStrategyType.CHAPTER_KEYWORD: ChapterKeywordSplitter,
    SplitStrategyType.RATIO: RatioSplitter,
    SplitStrategyType.FIXED_COUNT: FixedCountSplitter,
}


class SplitterService:
    """Service coordinating preview and execution of text splitting strategies."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def preview(
        self,
        *,
        project_id: str,
        text: str,
        strategy: SplitStrategyType,
        parameters: Dict[str, Any] | None = None,
    ) -> SplitPreviewResult:
        """Run a split strategy without writing files."""

        safe_project_id = self._ensure_safe_project_id(project_id)
        typed_parameters = self._coerce_parameters(strategy, parameters or {})
        splitter = self._build_splitter(strategy, typed_parameters)
        segments = splitter.split(text)
        stats = self._compute_segment_stats(segments)
        total_bytes = len(text.encode("utf-8"))
        sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return SplitPreviewResult(
            project_id=safe_project_id,
            strategy=strategy,
            parameters=typed_parameters.model_dump(),
            segments=stats,
            total_characters=len(text),
            total_bytes=total_bytes,
            source_sha256=sha256,
        )

    def execute(
        self,
        *,
        project_id: str,
        text: str,
        strategy: SplitStrategyType,
        parameters: Dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> SplitExecutionResult:
        """Run a split strategy and persist outputs to the filesystem."""

        preview_result = self.preview(
            project_id=project_id,
            text=text,
            strategy=strategy,
            parameters=parameters,
        )
        project_dir = self._resolve_project_directory(preview_result.project_id)
        output_dir = project_dir / "splits"
        self._prepare_output_directory(output_dir, overwrite=overwrite)

        written_files: List[str] = []
        for segment in preview_result.segments:
            file_path = output_dir / segment.filename
            file_path.write_text(segment.text, encoding="utf-8")
            written_files.append(segment.filename)

        metadata_path = output_dir / "metadata.json"
        metadata = self._build_metadata(preview_result, written_files)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        return SplitExecutionResult(
            preview=preview_result,
            output_directory=output_dir,
            metadata_path=metadata_path,
            written_files=written_files,
        )

    def _compute_segment_stats(self, segments: Iterable[SplitSegment]) -> List[SegmentStats]:
        stats: List[SegmentStats] = []
        byte_cursor = 0
        for segment in segments:
            byte_start = byte_cursor
            byte_end = byte_start + segment.byte_count
            stats.append(
                SegmentStats(
                    index=segment.index,
                    start_offset=segment.start,
                    end_offset=segment.end,
                    byte_start_offset=byte_start,
                    byte_end_offset=byte_end,
                    character_count=segment.character_count,
                    byte_count=segment.byte_count,
                    text=segment.text,
                )
            )
            byte_cursor = byte_end
        return stats

    def _build_splitter(
        self, strategy: SplitStrategyType, parameters: StrategyParameter
    ) -> TextSplitter:
        factory = _STRATEGY_BUILDERS.get(strategy)
        if factory is None:
            raise InvalidStrategyError(strategy.value)
        return factory(parameters)  # type: ignore[arg-type]

    def _coerce_parameters(
        self, strategy: SplitStrategyType, parameters: Dict[str, Any]
    ) -> StrategyParameter:
        try:
            return parse_strategy_parameters(strategy, parameters)
        except ValidationError as exc:
            raise StrategyConfigurationError(
                "Invalid strategy parameters",
                details={
                    "strategy": strategy.value,
                    "errors": exc.errors(),
                },
            ) from exc
        except ValueError as exc:
            message = str(exc)
            if "Unsupported strategy" in message:
                raise InvalidStrategyError(strategy.value) from exc
            raise StrategyConfigurationError(
                message,
                details={"strategy": strategy.value},
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive guard
            raise StrategyConfigurationError(
                "Invalid strategy parameters",
                details={"strategy": strategy.value},
            ) from exc

    def _ensure_safe_project_id(self, project_id: str) -> str:
        if not project_id or not project_id.strip():
            raise ProjectPathError(project_id)
        if not _PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ProjectPathError(project_id)
        parts = Path(project_id)
        if parts.is_absolute() or ".." in parts.parts:
            raise ProjectPathError(project_id)
        return project_id

    def _resolve_project_directory(self, project_id: str) -> Path:
        base_projects_dir = self._settings.paths.projects_dir
        project_dir = (base_projects_dir / project_id).resolve()
        if not str(project_dir).startswith(str(base_projects_dir.resolve())):
            raise ProjectPathError(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def _prepare_output_directory(self, output_dir: Path, *, overwrite: bool) -> None:
        if output_dir.exists():
            if not overwrite:
                existing_outputs = [
                    entry
                    for entry in output_dir.glob("*.txt")
                    if entry.is_file() and entry.name[:-4].isdigit()
                ]
                if existing_outputs:
                    raise SplitExecutionError(
                        "Existing split artefacts found",
                        details={"path": str(output_dir)},
                    )
            else:
                for entry in output_dir.iterdir():
                    if entry.is_file() and entry.suffix == ".txt" and entry.name[:-4].isdigit():
                        entry.unlink()
                metadata_file = output_dir / "metadata.json"
                if metadata_file.exists():
                    metadata_file.unlink()
        else:
            output_dir.mkdir(parents=True, exist_ok=True)

    def _build_metadata(
        self, preview: SplitPreviewResult, files: List[str]
    ) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        segments_payload = []
        for segment in preview.segments:
            segments_payload.append(
                {
                    "index": segment.index,
                    "file": segment.filename,
                    "start_offset": segment.start_offset,
                    "end_offset": segment.end_offset,
                    "byte_start_offset": segment.byte_start_offset,
                    "byte_end_offset": segment.byte_end_offset,
                    "character_count": segment.character_count,
                    "byte_count": segment.byte_count,
                }
            )

        return {
            "project_id": preview.project_id,
            "strategy": preview.strategy.value,
            "parameters": preview.parameters,
            "total_segments": len(preview.segments),
            "total_characters": preview.total_characters,
            "total_bytes": preview.total_bytes,
            "source_sha256": preview.source_sha256,
            "generated_at": timestamp,
            "files": files,
            "segments": segments_payload,
        }


__all__ = [
    "SegmentStats",
    "SplitPreviewResult",
    "SplitExecutionResult",
    "SplitterService",
]
