from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.core.agents as agents_module
import app.core.settings as settings_module


@pytest.fixture()
def runtime_environment(tmp_path, monkeypatch) -> Path:
    base_dir = tmp_path / "runtime"
    config_dir = base_dir / "config"
    data_dir = base_dir / "data"
    monkeypatch.setenv("APP_BASE_DIR", str(base_dir))
    monkeypatch.setenv("APP_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    return base_dir


@pytest.fixture()
def client(runtime_environment: Path) -> TestClient:
    settings_module.get_settings.cache_clear()
    agents_module.get_agents_service.cache_clear()

    import app.main as main_module

    importlib.reload(main_module)
    application = main_module.create_application()

    with TestClient(application) as test_client:
        yield test_client
