from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_settings_roundtrip(client: TestClient, runtime_environment: Path) -> None:
    initial_response = client.get("/settings")
    assert initial_response.status_code == 200
    initial_payload = initial_response.json()
    assert initial_payload["success"] is True

    update_payload = {
        "provider": {"base_url": "https://api.example.com", "api_key": "secret-key"},
        "prompts": {"default_prompt": "You are a helpful assistant.", "tone": "friendly"},
    }
    update_response = client.put("/settings", json=update_payload)
    assert update_response.status_code == 200
    update_body = update_response.json()
    assert update_body["success"] is True
    assert update_body["data"]["provider"]["base_url"] == "https://api.example.com"
    assert update_body["data"]["prompts"]["tone"] == "friendly"

    stored_path = runtime_environment / "config" / "app-settings.json"
    assert stored_path.exists()
    with stored_path.open("r", encoding="utf-8") as handle:
        persisted = json.load(handle)
    assert persisted["provider"]["api_key"] == "secret-key"
    assert persisted["prompts"]["default_prompt"] == "You are a helpful assistant."

    roundtrip_response = client.get("/settings")
    assert roundtrip_response.status_code == 200
    roundtrip_body = roundtrip_response.json()
    assert roundtrip_body["data"]["provider"]["base_url"] == "https://api.example.com"


def test_reload_agents_endpoint(client: TestClient, runtime_environment: Path) -> None:
    response = client.post("/settings/agents/reload")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["reloaded"] is True
    manifest_path = Path(data["manifest_path"])
    assert manifest_path.exists()
    expected_path = runtime_environment / "config" / "agents.md"
    assert manifest_path == expected_path
    assert data["version"]
