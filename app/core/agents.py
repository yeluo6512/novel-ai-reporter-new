"""Agents manifest management service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .settings import Settings, get_settings


class AgentsManifestMetadata(BaseModel):
    """Metadata describing the agents manifest file."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    version: str = Field(..., description="Version identifier for the manifest")
    generated_at: datetime | None = Field(
        default=None, description="Timestamp sourced from the manifest content"
    )
    cached_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the manifest content was cached",
    )
    file_path: Path = Field(..., description="Filesystem path of the manifest file")
    last_modified: datetime | None = Field(
        default=None, description="Filesystem modified timestamp"
    )


class AgentsManifest(BaseModel):
    """In-memory representation of the agents manifest."""

    content: str = Field(..., description="Raw Markdown content of the manifest")
    metadata: AgentsManifestMetadata


@dataclass
class _CachedManifest:
    manifest: AgentsManifest
    modified_time: float


class AgentsService:
    """Service responsible for managing the agents manifest lifecycle."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._lock = RLock()
        self._cache: _CachedManifest | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    def initialize(self) -> None:
        """Ensure required manifest assets are available on startup."""

        self.settings.ensure_directories()
        self._ensure_manifest_exists()
        self.get_manifest(force_refresh=True)

    def shutdown(self) -> None:
        """Release any cached state when the application stops."""

        with self._lock:
            self._cache = None

    def prepare_for_task(self) -> AgentsManifest:
        """Refresh the manifest before executing a task that depends on it."""

        return self.get_manifest(force_refresh=True)

    def get_manifest(self, force_refresh: bool = False) -> AgentsManifest:
        """Return the cached manifest, reloading it from disk if required."""

        manifest_path = self.settings.agents_manifest_path
        with self._lock:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            if not manifest_path.exists():
                self._write_default_manifest(manifest_path)

            stat_result = manifest_path.stat()
            needs_refresh = (
                force_refresh
                or self._cache is None
                or self._cache.modified_time != stat_result.st_mtime
            )

            if needs_refresh:
                content = manifest_path.read_text(encoding="utf-8")
                metadata = self._build_metadata(content, manifest_path, stat_result.st_mtime)
                manifest = AgentsManifest(content=content, metadata=metadata)
                self._cache = _CachedManifest(
                    manifest=manifest, modified_time=stat_result.st_mtime
                )

            return self._cache.manifest

    def invalidate_cache(self) -> None:
        """Explicitly clear the cached manifest."""

        with self._lock:
            self._cache = None

    def _ensure_manifest_exists(self) -> None:
        manifest_path = self.settings.agents_manifest_path
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not manifest_path.exists():
            self._write_default_manifest(manifest_path)

    def _write_default_manifest(self, manifest_path: Path) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        version = self.settings.app_version
        default_content = (
            "# Agents Manifest\n\n"
            f"Version: {version}\n"
            f"Generated: {timestamp}\n\n"
            "Describe available agents in this file.\n"
            "- Provide an overview of each agent's purpose.\n"
            "- Document configuration parameters and capabilities.\n"
        )
        manifest_path.write_text(default_content, encoding="utf-8")

    def _build_metadata(
        self, content: str, manifest_path: Path, modified_time: float
    ) -> AgentsManifestMetadata:
        version = self._extract_line_value(content, "version") or self.settings.app_version
        generated_raw = self._extract_line_value(content, "generated")
        generated_at = self._parse_datetime(generated_raw)
        last_modified = datetime.fromtimestamp(modified_time, tz=timezone.utc)
        return AgentsManifestMetadata(
            version=version,
            generated_at=generated_at,
            cached_at=datetime.now(timezone.utc),
            file_path=manifest_path,
            last_modified=last_modified,
        )

    @staticmethod
    def _extract_line_value(content: str, key: str) -> str | None:
        key_prefix = f"{key.lower()}:"
        for line in content.splitlines():
            line_lower = line.lower().strip()
            if line_lower.startswith(key_prefix):
                return line.split(":", 1)[1].strip()
        return None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        cleaned = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed


@lru_cache()
def get_agents_service() -> AgentsService:
    """Provide a singleton instance of :class:`AgentsService`."""

    return AgentsService()
