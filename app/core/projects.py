"""Filesystem-backed repository for managing project workspaces."""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from fastapi import UploadFile

from ..models.project import ProjectArtifact, ProjectDetail, ProjectFileInfo
from .settings import Settings

_METADATA_FILENAME = "metadata.json"
_UPLOADS_SUBDIR = "uploads"
_ARTIFACTS_SUBDIR = "artifacts"
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB
_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,127}$")


class ProjectError(Exception):
    """Base exception for project repository errors."""


class InvalidProjectNameError(ProjectError):
    """Raised when a provided project name cannot be safely normalised."""


class InvalidProjectUploadError(ProjectError):
    """Raised when an uploaded file is invalid or unsupported."""


class ProjectAlreadyExistsError(ProjectError):
    """Raised when attempting to create a project that already exists."""


class ProjectNotFoundError(ProjectError):
    """Raised when a requested project cannot be located."""


class ProjectsRepository:
    """Repository providing CRUD operations for filesystem-backed projects."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._projects_dir = settings.paths.projects_dir
        self._projects_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._projects_dir

    def list_projects(self) -> list[ProjectDetail]:
        projects: list[ProjectDetail] = []
        for entry in sorted(self._projects_dir.iterdir(), key=lambda item: item.name):
            if not entry.is_dir():
                continue
            try:
                project = self._load_project(entry)
            except ProjectError:
                continue
            projects.append(project)
        projects.sort(key=lambda p: (p.created_at, p.identifier))
        return projects

    def get_project(self, identifier: str) -> ProjectDetail:
        project_dir = self._resolve_project_dir(identifier)
        if not project_dir.exists() or not project_dir.is_dir():
            raise ProjectNotFoundError(f"Project '{identifier}' was not found.")
        return self._load_project(project_dir)

    async def create_project(
        self,
        novel_name: str,
        *,
        display_name: str | None,
        description: str | None,
        tags: Sequence[str] | None,
        upload: UploadFile,
    ) -> ProjectDetail:
        slug = self._normalise_name(novel_name)
        project_dir = (self._projects_dir / slug).resolve()
        self._assert_within_base(project_dir)
        if project_dir.exists():
            raise ProjectAlreadyExistsError(
                f"A project with identifier '{slug}' already exists."
            )

        created_at = datetime.now(timezone.utc)
        upload_dir = project_dir / _UPLOADS_SUBDIR
        artifacts_dir = project_dir / _ARTIFACTS_SUBDIR

        try:
            upload_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            upload_info = await self._write_upload(project_dir, upload_dir, slug, upload)

            project = ProjectDetail(
                identifier=slug,
                name=self._clean_name(display_name) or self._derive_display_name(novel_name),
                description=self._clean_description(description),
                tags=self._normalise_tags(tags),
                workspace_path=project_dir,
                created_at=created_at,
                updated_at=created_at,
                original_file=upload_info,
                artifacts=[],
            )
            self._write_metadata(project_dir, project)
        except Exception:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise

        return self._load_project(project_dir)

    def update_project(
        self,
        identifier: str,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> ProjectDetail:
        project_dir = self._resolve_project_dir(identifier)
        if not project_dir.exists() or not project_dir.is_dir():
            raise ProjectNotFoundError(f"Project '{identifier}' was not found.")

        project = self._load_project(project_dir)
        updates: dict[str, object] = {}
        if name is not None:
            cleaned_name = self._clean_name(name)
            if not cleaned_name:
                raise InvalidProjectNameError("Project name cannot be empty after cleaning.")
            updates["name"] = cleaned_name
        if description is not None:
            updates["description"] = self._clean_description(description)
        if tags is not None:
            updates["tags"] = self._normalise_tags(tags)
        updates["updated_at"] = datetime.now(timezone.utc)

        updated_project = project.model_copy(update=updates)
        self._write_metadata(project_dir, updated_project)
        return self._load_project(project_dir)

    def delete_project(self, identifier: str) -> None:
        project_dir = self._resolve_project_dir(identifier)
        if not project_dir.exists() or not project_dir.is_dir():
            raise ProjectNotFoundError(f"Project '{identifier}' was not found.")
        shutil.rmtree(project_dir)

    # Internal helpers -----------------------------------------------------

    def _load_project(self, project_dir: Path) -> ProjectDetail:
        metadata_path = project_dir / _METADATA_FILENAME
        if not metadata_path.exists():
            raise ProjectNotFoundError("Project metadata is missing.")
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        project = ProjectDetail.model_validate(raw)
        project.workspace_path = project_dir
        project.artifacts = self._collect_artifacts(project_dir)
        return project

    def _write_metadata(self, project_dir: Path, project: ProjectDetail) -> None:
        metadata_path = project_dir / _METADATA_FILENAME
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(project.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _collect_artifacts(self, project_dir: Path) -> list[ProjectArtifact]:
        artifacts_dir = project_dir / _ARTIFACTS_SUBDIR
        if not artifacts_dir.exists():
            return []
        artifacts: list[ProjectArtifact] = []
        for path in sorted(artifacts_dir.rglob("*")):
            if not path.is_file():
                continue
            stat_result = path.stat()
            artifacts.append(
                ProjectArtifact(
                    name=path.name,
                    relative_path=str(path.relative_to(project_dir)),
                    size=stat_result.st_size,
                    modified_at=datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc),
                )
            )
        return artifacts

    async def _write_upload(
        self,
        project_dir: Path,
        upload_dir: Path,
        slug: str,
        upload: UploadFile,
    ) -> ProjectFileInfo:
        filename = self._normalise_upload_filename(upload.filename, slug)
        destination = (upload_dir / filename).resolve()
        self._assert_within_base(destination)

        bytes_written = 0
        chunk_count = 0
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as buffer:
            while True:
                chunk = await upload.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                buffer.write(chunk)
                bytes_written += len(chunk)
                chunk_count += 1
        await upload.close()

        uploaded_at = datetime.now(timezone.utc)
        return ProjectFileInfo(
            filename=filename,
            content_type=upload.content_type,
            size=bytes_written,
            chunks=chunk_count,
            uploaded_at=uploaded_at,
            relative_path=str(destination.relative_to(project_dir)),
        )

    def _resolve_project_dir(self, identifier: str) -> Path:
        slug = self._validate_identifier(identifier)
        project_dir = (self._projects_dir / slug).resolve()
        self._assert_within_base(project_dir)
        return project_dir

    def _normalise_tags(self, tags: Sequence[str] | None) -> list[str]:
        if not tags:
            return []
        normalised = []
        for tag in tags:
            cleaned = tag.strip()
            if cleaned:
                normalised.append(cleaned)
        # Preserve original casing for readability but ensure stable ordering
        return sorted(dict.fromkeys(normalised), key=str.lower)

    @staticmethod
    def _clean_name(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _clean_description(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def _normalise_name(self, value: str) -> str:
        cleaned = self._clean_name(value)
        if not cleaned:
            raise InvalidProjectNameError("Project name cannot be empty.")
        ascii_name = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
        ascii_name = ascii_name.lower()
        ascii_name = re.sub(r"[^a-z0-9\s\-_]", "", ascii_name)
        ascii_name = re.sub(r"[\s_]+", "-", ascii_name)
        slug = ascii_name.strip("-")
        if not slug:
            raise InvalidProjectNameError("Project name does not contain valid characters.")
        if not _IDENTIFIER_PATTERN.fullmatch(slug):
            raise InvalidProjectNameError(
                "Project name must contain only alphanumeric characters, hyphens, or underscores "
                "and be between 1 and 128 characters in length."
            )
        return slug

    @staticmethod
    def _derive_display_name(value: str) -> str:
        cleaned = value.strip()
        return cleaned or value

    def _normalise_upload_filename(self, filename: str | None, slug: str) -> str:
        candidate = filename or f"{slug}.txt"
        candidate = Path(candidate).name
        ascii_name = unicodedata.normalize("NFKD", candidate).encode("ascii", "ignore").decode("ascii")
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", ascii_name)
        if not ascii_name:
            ascii_name = f"{slug}.txt"
        if not ascii_name.lower().endswith(".txt"):
            raise InvalidProjectUploadError("Only '.txt' manuscript uploads are supported.")
        return ascii_name

    def _validate_identifier(self, identifier: str) -> str:
        cleaned = identifier.strip().lower()
        if not cleaned:
            raise ProjectNotFoundError("Project identifier cannot be empty.")
        if not _IDENTIFIER_PATTERN.fullmatch(cleaned):
            raise ProjectNotFoundError("Project identifier contains unsupported characters.")
        return cleaned

    def _assert_within_base(self, path: Path) -> None:
        base = self._projects_dir.resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise InvalidProjectNameError("Resolved path escapes the projects directory.") from exc
