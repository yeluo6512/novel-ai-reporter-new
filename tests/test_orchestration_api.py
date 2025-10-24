from __future__ import annotations

from importlib import reload
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def api_manifest() -> str:
    return (
        "# Agents Manifest\n"
        "\n"
        "## analysis\n"
        "API analysis guidance.\n"
        "\n"
        "## integration\n"
        "API integration directives.\n"
        "\n"
        "## finalization\n"
        "API finalisation summary instructions.\n"
    )


def test_generation_and_final_report_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, api_manifest: str) -> None:
    base_dir = tmp_path / "runtime"
    config_dir = base_dir / "config"
    data_dir = base_dir / "data"

    monkeypatch.setenv("APP_BASE_DIR", str(base_dir))
    monkeypatch.setenv("APP_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))

    import app.core.settings as settings_module
    reload(settings_module)
    import app.core.agents as agents_module
    reload(agents_module)
    import app.services.orchestration as orchestration_module
    reload(orchestration_module)
    import app.api.routes.orchestration as routes_module
    reload(routes_module)
    import app.api as api_module
    reload(api_module)
    import app.main as main_module
    reload(main_module)

    app = main_module.create_application()

    with TestClient(app) as client:
        settings = settings_module.get_settings()
        settings.ensure_directories()

        manifest_path = settings.agents_manifest_path
        manifest_path.write_text(api_manifest, encoding="utf-8")
        agents_module.get_agents_service().invalidate_cache()

        project_id = "api-project"
        splits_dir = settings.paths.projects_dir / project_id / "splits"
        splits_dir.mkdir(parents=True, exist_ok=True)
        (splits_dir / "0.txt").write_text("Segment zero via API.", encoding="utf-8")
        (splits_dir / "1.txt").write_text("Segment one via API.", encoding="utf-8")

        response = client.post(
            f"/projects/{project_id}/reports/generate",
            json={"cascade": True},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["status"] == "pending"

        status_response = client.get(f"/projects/{project_id}/reports/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["success"] is True
        assert status_payload["data"]["status"] == "completed"

        final_response = client.get(f"/projects/{project_id}/reports/final")
        assert final_response.status_code == 200
        final_payload = final_response.json()
        assert final_payload["success"] is True
        assert "Final Report" in final_payload["data"]["content"]

        manual_content = "# Final Report\n\nManually curated content.\n"
        update_response = client.put(
            f"/projects/{project_id}/reports/final",
            json={"content": manual_content},
        )
        assert update_response.status_code == 200
        update_payload = update_response.json()
        assert update_payload["success"] is True
        assert update_payload["data"]["message"] == "Final report updated via API"

        refreshed_final = client.get(f"/projects/{project_id}/reports/final")
        assert refreshed_final.status_code == 200
        assert refreshed_final.json()["data"]["content"] == manual_content
