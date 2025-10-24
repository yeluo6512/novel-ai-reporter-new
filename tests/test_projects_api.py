from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_project_crud_flow(client: TestClient, runtime_environment: Path) -> None:
    projects_root = runtime_environment / "data" / "projects"

    create_response = client.post(
        "/projects",
        data={
            "novel_name": "My Novel Title",
            "display_name": "My Novel Title",
            "description": "A sample description",
            "tags": "fantasy, adventure",
        },
        files={"upload": ("novel.txt", b"Once upon a time", "text/plain")},
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["success"] is True
    project_data = payload["data"]["project"]
    project_id = project_data["identifier"]
    assert project_id == "my-novel-title"
    original_file = project_data["original_file"]
    assert original_file["filename"] == "novel.txt"
    assert original_file["size"] == len(b"Once upon a time")
    assert original_file["chunks"] >= 1

    project_dir = projects_root / project_id
    assert project_dir.exists()
    assert (project_dir / "uploads" / "novel.txt").exists()
    assert (project_dir / "metadata.json").exists()

    list_response = client.get("/projects")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["success"] is True
    assert len(list_payload["data"]["items"]) == 1

    detail_response = client.get(f"/projects/{project_id}")
    assert detail_response.status_code == 200

    update_response = client.put(
        f"/projects/{project_id}",
        json={
            "name": "Updated Title",
            "description": "Updated description",
            "tags": ["updated", "fantasy"],
        },
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["data"]["name"] == "Updated Title"
    assert set(update_payload["data"]["tags"]) == {"updated", "fantasy"}

    delete_response = client.delete(f"/projects/{project_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["identifier"] == project_id
    assert not project_dir.exists()

    missing_response = client.get(f"/projects/{project_id}")
    assert missing_response.status_code == 404
    missing_payload = missing_response.json()
    assert missing_payload["success"] is False


def test_rejects_non_text_upload(client: TestClient) -> None:
    response = client.post(
        "/projects",
        data={"novel_name": "Sample"},
        files={"upload": ("sample.pdf", b"%PDF-1.7", "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_project_upload"


def test_list_projects_when_empty(client: TestClient) -> None:
    response = client.get("/projects")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["items"] == []
