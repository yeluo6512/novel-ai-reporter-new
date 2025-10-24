"""Persistence utilities for application-level preference data."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from ..models.settings import ApplicationSettingsPayload, ProviderConfiguration
from .settings import Settings

_DEFAULT_FILENAME = "app-settings.json"


class ApplicationSettingsStore:
    """Filesystem-backed persistence for adjustable application settings."""

    def __init__(self, settings: Settings, filename: str = _DEFAULT_FILENAME) -> None:
        self._settings = settings
        self._path = (settings.paths.config_dir / filename).resolve()
        self._lock = RLock()

    @property
    def path(self) -> Path:
        """Return the resolved path to the persisted settings file."""

        return self._path

    def read(self) -> ApplicationSettingsPayload:
        """Load persisted settings, falling back to defaults when absent."""

        with self._lock:
            if not self._path.exists():
                payload = self._default_payload()
                self._persist_locked(payload)
                return payload

            raw = json.loads(self._path.read_text(encoding="utf-8"))

        return ApplicationSettingsPayload.model_validate(raw)

    def write(self, payload: ApplicationSettingsPayload) -> ApplicationSettingsPayload:
        """Persist the supplied settings payload to disk."""

        with self._lock:
            self._persist_locked(payload)
        return payload

    # Internal helpers -----------------------------------------------------

    def _persist_locked(self, payload: ApplicationSettingsPayload) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serialized = payload.model_dump(mode="json")
        self._path.write_text(
            json.dumps(serialized, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _default_payload(self) -> ApplicationSettingsPayload:
        provider_defaults = ProviderConfiguration(
            base_url=self._settings.provider_base_url,
            api_key=self._settings.provider_api_key,
        )
        return ApplicationSettingsPayload(provider=provider_defaults)
