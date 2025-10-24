"""Orchestration service implementing analysis, integration, and final report workflows."""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterable, Sequence

from ..core.agents import AgentsService, get_agents_service
from ..core.settings import Settings, get_settings
from ..models.orchestration import (
    OrchestrationStatus,
    StageName,
    StageStatus,
    TaskState,
)

__all__ = ["OrchestrationService", "OrchestrationError", "TaskConflictError", "ProjectWorkspaceError"]

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _StageTracker:
    name: StageName
    state: TaskState = TaskState.IDLE
    detail: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def as_model(self) -> StageStatus:
        return StageStatus(
            stage=self.name,
            status=self.state,
            detail=self.detail,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


@dataclass
class _ProjectTracker:
    project_id: str
    stages: dict[StageName, _StageTracker] = field(default_factory=dict)
    state: TaskState = TaskState.IDLE
    message: str | None = None
    requested_segments: Sequence[int] | None = None
    cascade: bool | None = None
    updated_at: datetime = field(default_factory=_now)
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.stages:
            self.stages = {
                StageName.ANALYSIS: _StageTracker(StageName.ANALYSIS),
                StageName.INTEGRATION: _StageTracker(StageName.INTEGRATION),
                StageName.FINALIZATION: _StageTracker(StageName.FINALIZATION),
            }

    def touch(self) -> None:
        self.updated_at = _now()

    def set_overall(self, state: TaskState, message: str | None = None) -> None:
        self.state = state
        if message is not None:
            self.message = message
        self.touch()

    def update_stage(
        self, stage: StageName, state: TaskState, detail: str | None = None
    ) -> None:
        tracker = self.stages[stage]
        now = _now()
        if state == TaskState.RUNNING:
            tracker.started_at = now
            tracker.completed_at = None
        elif state in {TaskState.COMPLETED, TaskState.FAILED}:
            tracker.completed_at = now
            tracker.started_at = tracker.started_at or now
        tracker.state = state
        tracker.detail = detail
        self.touch()

    def as_model(self) -> OrchestrationStatus:
        return OrchestrationStatus(
            project_id=self.project_id,
            status=self.state,
            stages=[self.stages[name].as_model() for name in StageName],
            message=self.message,
            requested_segments=list(self.requested_segments) if self.requested_segments is not None else None,
            cascade=self.cascade,
            updated_at=self.updated_at,
            error=self.error,
        )


@dataclass
class _Segment:
    index: int
    source_path: Path

    @property
    def analysis_path(self) -> Path:
        return self.source_path.with_suffix(".md")


@dataclass
class ProjectWorkspace:
    project_id: str
    project_dir: Path
    splits_dir: Path
    integration_dir: Path
    final_report_path: Path


class OrchestrationError(Exception):
    """Base exception for orchestration failures."""


class TaskConflictError(OrchestrationError):
    """Raised when attempting to start a task while another is running."""


class ProjectWorkspaceError(OrchestrationError):
    """Raised when the project workspace is misconfigured or incomplete."""


class OrchestrationService:
    """Coordination service for executing and tracking report workflows."""

    def __init__(
        self,
        settings: Settings | None = None,
        agents_service: AgentsService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._agents_service = agents_service or get_agents_service()
        self._status_lock = RLock()
        self._project_states: dict[str, _ProjectTracker] = {}
        self._project_locks: dict[str, RLock] = {}
        self._settings.ensure_directories()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def agents_service(self) -> AgentsService:
        return self._agents_service

    def get_status(self, project_id: str) -> OrchestrationStatus:
        with self._status_lock:
            tracker = self._project_states.get(project_id)
            if tracker is None:
                tracker = _ProjectTracker(project_id=project_id)
                self._project_states[project_id] = tracker
            return tracker.as_model()

    def start_background_task(
        self,
        project_id: str,
        background_tasks,
        regenerate_segments: Sequence[int] | None = None,
        cascade: bool = True,
    ) -> OrchestrationStatus:
        workspace = self._resolve_workspace(project_id)
        tracker = self._prepare_tracker(project_id, regenerate_segments, cascade)
        background_tasks.add_task(
            self._execute_pipeline_with_tracking,
            workspace,
            regenerate_segments,
            cascade,
        )
        return tracker.as_model()

    def generate_reports(
        self,
        project_id: str,
        regenerate_segments: Sequence[int] | None = None,
        cascade: bool = True,
    ) -> OrchestrationStatus:
        workspace = self._resolve_workspace(project_id)
        tracker = self._prepare_tracker(project_id, regenerate_segments, cascade)
        self._execute_pipeline_with_tracking(workspace, regenerate_segments, cascade)
        return tracker.as_model()

    def read_final_report(self, project_id: str) -> str:
        workspace = self._resolve_workspace(project_id)
        if not workspace.final_report_path.exists():
            raise ProjectWorkspaceError(
                f"Final report has not been generated for project {project_id!r}."
            )
        return workspace.final_report_path.read_text(encoding="utf-8")

    def save_final_report(self, project_id: str, content: str) -> OrchestrationStatus:
        workspace = self._resolve_workspace(project_id)
        workspace.final_report_path.parent.mkdir(parents=True, exist_ok=True)
        workspace.final_report_path.write_text(content, encoding="utf-8")
        with self._status_lock:
            tracker = self._project_states.setdefault(
                project_id, _ProjectTracker(project_id=project_id)
            )
            tracker.message = "Final report updated via API"
            tracker.touch()
            final_stage = tracker.stages[StageName.FINALIZATION]
            final_stage.detail = "Final report edited via API"
            final_stage.completed_at = _now()
            if final_stage.started_at is None:
                final_stage.started_at = final_stage.completed_at
            if final_stage.state in {TaskState.IDLE, TaskState.PENDING}:
                final_stage.state = TaskState.COMPLETED
            return tracker.as_model()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _prepare_tracker(
        self,
        project_id: str,
        regenerate_segments: Sequence[int] | None,
        cascade: bool,
    ) -> _ProjectTracker:
        with self._status_lock:
            tracker = self._project_states.get(project_id)
            if tracker is None:
                tracker = _ProjectTracker(project_id=project_id)
                self._project_states[project_id] = tracker
            if tracker.state in {TaskState.PENDING, TaskState.RUNNING}:
                raise TaskConflictError(
                    f"Orchestration already running for project {project_id!r}."
                )
            tracker.state = TaskState.PENDING
            tracker.message = "Task queued"
            tracker.requested_segments = list(regenerate_segments) if regenerate_segments is not None else None
            tracker.cascade = cascade
            tracker.error = None
            for stage in StageName:
                tracker.stages[stage] = _StageTracker(name=stage)
            tracker.touch()
            return tracker

    def _execute_pipeline_with_tracking(
        self,
        workspace: ProjectWorkspace,
        regenerate_segments: Sequence[int] | None,
        cascade: bool,
    ) -> None:
        tracker = self._project_states[workspace.project_id]
        tracker.set_overall(TaskState.RUNNING, "Starting orchestration pipeline")

        project_lock = self._project_locks.setdefault(workspace.project_id, RLock())
        try:
            with project_lock:
                try:
                    self._run_analysis(workspace, tracker, regenerate_segments)
                except Exception as exc:  # noqa: BLE001
                    with self._status_lock:
                        tracker.update_stage(
                            StageName.ANALYSIS, TaskState.FAILED, detail=str(exc)
                        )
                    raise

                try:
                    self._run_integration(workspace, tracker, regenerate_segments, cascade)
                except Exception as exc:  # noqa: BLE001
                    with self._status_lock:
                        tracker.update_stage(
                            StageName.INTEGRATION, TaskState.FAILED, detail=str(exc)
                        )
                    raise

                try:
                    self._run_finalization(workspace, tracker)
                except Exception as exc:  # noqa: BLE001
                    with self._status_lock:
                        tracker.update_stage(
                            StageName.FINALIZATION, TaskState.FAILED, detail=str(exc)
                        )
                    raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Orchestration failed for project %s", workspace.project_id)
            with self._status_lock:
                tracker.error = str(exc)
                tracker.set_overall(TaskState.FAILED, "Orchestration failed")
                final_stage_state = tracker.stages[StageName.FINALIZATION].state
                if final_stage_state not in {TaskState.FAILED, TaskState.COMPLETED}:
                    tracker.update_stage(
                        StageName.FINALIZATION, TaskState.FAILED, detail="Aborted"
                    )
            raise

        with self._status_lock:
            tracker.error = None
            tracker.set_overall(TaskState.COMPLETED, "Orchestration completed successfully")

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------
    def _run_analysis(
        self,
        workspace: ProjectWorkspace,
        tracker: _ProjectTracker,
        regenerate_segments: Sequence[int] | None,
    ) -> None:
        with self._status_lock:
            tracker.update_stage(StageName.ANALYSIS, TaskState.RUNNING, detail="Starting analysis")

        manifest = self.agents_service.prepare_for_task()
        directive = self._select_stage_directive(manifest.content, StageName.ANALYSIS)

        segments = list(self._load_segments(workspace.splits_dir))
        if not segments:
            raise ProjectWorkspaceError(
                f"No split segments found in {workspace.splits_dir}"
            )

        requested = set(regenerate_segments or [])
        generated_count = 0
        for segment in segments:
            should_generate = (
                regenerate_segments is None
                or not regenerate_segments
                or segment.index in requested
                or not segment.analysis_path.exists()
            )
            if should_generate:
                text = segment.source_path.read_text(encoding="utf-8")
                analysis = self._render_analysis(segment.index, segment.source_path.name, text, directive)
                segment.analysis_path.write_text(analysis, encoding="utf-8")
                generated_count += 1
        detail_message = f"Generated analysis for {generated_count} segment(s)"
        with self._status_lock:
            tracker.update_stage(StageName.ANALYSIS, TaskState.COMPLETED, detail=detail_message)

    def _run_integration(
        self,
        workspace: ProjectWorkspace,
        tracker: _ProjectTracker,
        regenerate_segments: Sequence[int] | None,
        cascade: bool,
    ) -> None:
        with self._status_lock:
            tracker.update_stage(StageName.INTEGRATION, TaskState.RUNNING, detail="Starting integration")

        manifest = self.agents_service.prepare_for_task()
        directive = self._select_stage_directive(manifest.content, StageName.INTEGRATION)

        segments = list(self._load_segments(workspace.splits_dir))
        analyses = {segment.index: segment.analysis_path for segment in segments if segment.analysis_path.exists()}
        if len(analyses) != len(segments):
            missing = sorted({seg.index for seg in segments} - set(analyses))
            raise ProjectWorkspaceError(
                f"Missing analysis reports for segment(s): {', '.join(map(str, missing))}"
            )

        workspace.integration_dir.mkdir(parents=True, exist_ok=True)

        requested = set(regenerate_segments or [])
        cascade_active = False

        integrations_written = 0
        for pair_index, first, second in self._pairwise(segments):
            integration_path = workspace.integration_dir / f"integrated_{pair_index}.md"

            if first is None or second is None:
                # Nothing to integrate when a trailing segment lacks a pair; remove stale output.
                if integration_path.exists():
                    integration_path.unlink()
                continue

            indices = [first.index, second.index]
            needs_update = False

            if regenerate_segments is None or not regenerate_segments:
                needs_update = True
            else:
                if any(index in requested for index in indices):
                    needs_update = True
                    if cascade:
                        cascade_active = True
                elif cascade_active:
                    needs_update = True

            if not integration_path.exists():
                needs_update = True

            if needs_update:
                text_a = first.source_path.read_text(encoding="utf-8")
                text_b = second.source_path.read_text(encoding="utf-8")
                analysis_a = analyses[first.index].read_text(encoding="utf-8")
                analysis_b = analyses[second.index].read_text(encoding="utf-8")
                integration_text = self._render_integration(
                    pair_index=pair_index,
                    directive=directive,
                    first=first,
                    second=second,
                    text_a=text_a,
                    text_b=text_b,
                    analysis_a=analysis_a,
                    analysis_b=analysis_b,
                )
                integration_path.write_text(integration_text, encoding="utf-8")
                integrations_written += 1
        detail_message = f"Ensured integration coverage for {integrations_written} pair(s)"
        with self._status_lock:
            tracker.update_stage(StageName.INTEGRATION, TaskState.COMPLETED, detail=detail_message)

    def _run_finalization(
        self,
        workspace: ProjectWorkspace,
        tracker: _ProjectTracker,
    ) -> None:
        with self._status_lock:
            tracker.update_stage(StageName.FINALIZATION, TaskState.RUNNING, detail="Compiling final report")

        manifest = self.agents_service.prepare_for_task()
        directive = self._select_stage_directive(manifest.content, StageName.FINALIZATION)

        segments = list(self._load_segments(workspace.splits_dir))
        analyses = {segment.index: segment.analysis_path for segment in segments if segment.analysis_path.exists()}
        if len(analyses) != len(segments):
            missing = sorted({seg.index for seg in segments} - set(analyses))
            raise ProjectWorkspaceError(
                f"Missing analysis reports for segment(s): {', '.join(map(str, missing))}"
            )

        sections: list[str] = []
        integrations: list[Path] = []

        for pair_index, first, second in self._pairwise(segments):
            integration_path = workspace.integration_dir / f"integrated_{pair_index}.md"
            if integration_path.exists() and second is not None:
                integrations.append(integration_path)
            else:
                # no integration (either missing or unmatched leftover)
                if first is not None:
                    sections.append(analyses[first.index].read_text(encoding="utf-8"))
                if second is not None and second.index in analyses:
                    sections.append(analyses[second.index].read_text(encoding="utf-8"))

        integrations.sort(key=lambda path: int(path.stem.split("_")[1]))
        integration_sections = [path.read_text(encoding="utf-8") for path in integrations]

        final_content = self._render_final_report(directive, integration_sections, sections)
        workspace.final_report_path.write_text(final_content, encoding="utf-8")

        detail_message = "Final report updated"
        with self._status_lock:
            tracker.update_stage(StageName.FINALIZATION, TaskState.COMPLETED, detail=detail_message)

    # ------------------------------------------------------------------
    # Workspace helpers
    # ------------------------------------------------------------------
    def _resolve_workspace(self, project_id: str) -> ProjectWorkspace:
        project_dir = self.settings.paths.projects_dir / project_id
        splits_dir = project_dir / "splits"
        integration_dir = project_dir / "integrations"
        final_report_path = project_dir / "final_report.md"

        if not splits_dir.exists() or not splits_dir.is_dir():
            raise ProjectWorkspaceError(
                f"Splits directory not found for project {project_id!r}: {splits_dir}"
            )
        project_dir.mkdir(parents=True, exist_ok=True)

        return ProjectWorkspace(
            project_id=project_id,
            project_dir=project_dir,
            splits_dir=splits_dir,
            integration_dir=integration_dir,
            final_report_path=final_report_path,
        )

    def _load_segments(self, splits_dir: Path) -> Iterable[_Segment]:
        segments: list[_Segment] = []
        source_extensions = {".txt", ".text", ".rst"}
        markdown_extensions = {".md", ".markdown"}
        allowed_extensions = source_extensions | markdown_extensions

        for entry in sorted(splits_dir.iterdir()):
            if not entry.is_file():
                continue
            suffix = entry.suffix.lower()
            if suffix not in allowed_extensions:
                continue
            try:
                index = int(entry.stem)
            except ValueError:
                continue

            if suffix in markdown_extensions:
                alternate_sources = [splits_dir / f"{index}{ext}" for ext in source_extensions]
                if any(candidate.exists() for candidate in alternate_sources):
                    # This is an analysis artefact co-located with the source file.
                    continue
                raise ProjectWorkspaceError(
                    f"Split segment {entry} uses a Markdown extension which conflicts with generated reports; "
                    "please rename the source file to use a non-Markdown extension (e.g. .txt)."
                )

            segments.append(_Segment(index=index, source_path=entry))

        segments.sort(key=lambda segment: segment.index)
        return segments

    @staticmethod
    def _pairwise(segments: Sequence[_Segment]):
        iterator = iter(segments)
        for pair_index, first in enumerate(iterator):
            second = next(iterator, None)
            yield pair_index, first, second

    # ------------------------------------------------------------------
    # Content rendering
    # ------------------------------------------------------------------
    @staticmethod
    def _trim_excerpt(text: str, max_length: int = 320) -> str:
        snippet = text.strip().replace("\r\n", "\n")
        if len(snippet) <= max_length:
            return snippet
        return snippet[: max_length - 3].rstrip() + "..."

    def _render_analysis(
        self,
        index: int,
        filename: str,
        text: str,
        directive: str,
    ) -> str:
        word_count = len(text.split())
        char_count = len(text)
        excerpt = self._trim_excerpt(text)
        directive_block = directive.strip() or "No directive provided."
        return textwrap.dedent(
            f"""
            # Segment {index} Analysis

            _Source file_: `{filename}`
            _Directive context_:
            {directive_block}

            ## Segment Metrics
            - Character count: {char_count}
            - Word count: {word_count}

            ## Source Excerpt
            {excerpt}
            """
        ).strip() + "\n"

    def _render_integration(
        self,
        pair_index: int,
        directive: str,
        first: _Segment | None,
        second: _Segment | None,
        text_a: str,
        text_b: str,
        analysis_a: str,
        analysis_b: str,
    ) -> str:
        directive_block = directive.strip() or "No directive provided."
        segments_info: list[str] = []
        excerpts: list[str] = []
        analyses_summary: list[str] = []

        if first is not None:
            segments_info.append(f"- Segment {first.index} (`{first.source_path.name}`)")
            excerpts.append(textwrap.dedent(
                f"""
                ### Segment {first.index} Excerpt
                {self._trim_excerpt(text_a)}
                """
            ).strip())
            analyses_summary.append(textwrap.dedent(
                f"""
                ### Segment {first.index} Highlights
                {self._trim_excerpt(analysis_a, 400)}
                """
            ).strip())
        if second is not None:
            segments_info.append(f"- Segment {second.index} (`{second.source_path.name}`)")
            excerpts.append(textwrap.dedent(
                f"""
                ### Segment {second.index} Excerpt
                {self._trim_excerpt(text_b)}
                """
            ).strip())
            analyses_summary.append(textwrap.dedent(
                f"""
                ### Segment {second.index} Highlights
                {self._trim_excerpt(analysis_b, 400)}
                """
            ).strip())

        combined_words = len((text_a + " " + text_b).split())
        combined_chars = len(text_a) + len(text_b)

        return textwrap.dedent(
            f"""
            # Integrated Report {pair_index}

            _Directive context_:
            {directive_block}

            ## Covered Segments
            {'\n'.join(segments_info)}

            ## Combined Metrics
            - Total characters: {combined_chars}
            - Total words: {combined_words}

            {'\n\n'.join(excerpts)}

            ## Analysis Summaries
            {'\n\n'.join(analyses_summary)}
            """
        ).strip() + "\n"

    def _render_final_report(
        self,
        directive: str,
        integration_sections: Sequence[str],
        residual_sections: Sequence[str],
    ) -> str:
        directive_block = directive.strip() or "No directive provided."
        sections: list[str] = []
        for idx, content in enumerate(integration_sections, start=1):
            sections.append(textwrap.dedent(
                f"""
                ## Integrated Summary {idx}

                {content.strip()}
                """
            ).strip())
        for idx, content in enumerate(residual_sections, start=1):
            sections.append(textwrap.dedent(
                f"""
                ## Residual Segment {idx}

                {content.strip()}
                """
            ).strip())
        body = "\n\n".join(sections)
        return textwrap.dedent(
            f"""
            # Final Report

            _Directive context_:
            {directive_block}

            {body}
            """
        ).strip() + "\n"

    # ------------------------------------------------------------------
    # Directive parsing
    # ------------------------------------------------------------------
    def _select_stage_directive(self, manifest: str, stage: StageName) -> str:
        lines = manifest.splitlines()
        normalized_stage = stage.value.lower()
        start_index: int | None = None
        start_level = 0

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            level = len(stripped) - len(stripped.lstrip('#'))
            header = stripped.lstrip('#').strip().lower()
            header = header.replace("stage", "").replace(":", "").strip()
            if header == normalized_stage:
                start_index = idx + 1
                start_level = level
                break

        if start_index is None:
            return manifest

        collected: list[str] = []
        for line in lines[start_index:]:
            stripped = line.strip()
            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip('#'))
                if level <= start_level:
                    break
            collected.append(line)

        result = "\n".join(collected).strip()
        return result or manifest

