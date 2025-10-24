"""Integration tests covering splitter preview and execution APIs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.main import create_application


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("APP_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()
    app = create_application()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_preview_character_count_handles_multibyte_characters(client: TestClient) -> None:
    text = "你好世界Hello世界"
    payload = {
        "project_id": "multibyte",
        "text": text,
        "strategy": "character_count",
        "parameters": {"max_characters": 5},
    }

    response = client.post("/splitter/preview", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    preview = body["data"]
    expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert preview["source_sha256"] == expected_hash

    segments = preview["segments"]
    cumulative_bytes = 0
    for segment in segments:
        excerpt = text[segment["start_offset"] : segment["end_offset"]]
        assert segment["character_count"] == len(excerpt)
        assert segment["byte_count"] == len(excerpt.encode("utf-8"))
        assert segment["byte_start_offset"] == cumulative_bytes
        cumulative_bytes += segment["byte_count"]
        assert segment["byte_end_offset"] == cumulative_bytes

    assert preview["total_characters"] == len(text)
    assert preview["total_bytes"] == len(text.encode("utf-8"))


def test_chapter_keyword_strategy_detects_chinese_chapters(client: TestClient) -> None:
    text = "第1章 序幕\n这里是第一章的内容。\n第2章 发展\n这里是第二章的内容。\n"
    payload = {
        "project_id": "novel",
        "text": text,
        "strategy": "chapter_keyword",
        "parameters": {},
    }

    response = client.post("/splitter/preview", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    segments = body["data"]["segments"]
    assert len(segments) == 2
    assert segments[0]["start_offset"] == 0
    second_chapter_index = text.index("第2章")
    assert segments[1]["start_offset"] == second_chapter_index


def test_execute_persists_files_and_metadata(client: TestClient) -> None:
    project_id = "execution"
    text = "Alpha section\nBeta section\nGamma section\nDelta section"
    preview_payload = {
        "project_id": project_id,
        "text": text,
        "strategy": "fixed_count",
        "parameters": {"segments": 3},
    }

    preview_response = client.post("/splitter/preview", json=preview_payload)
    assert preview_response.status_code == 200
    preview_segments = preview_response.json()["data"]["segments"]

    execute_payload = {
        **preview_payload,
        "overwrite": True,
    }
    execute_response = client.post("/splitter/execute", json=execute_payload)
    assert execute_response.status_code == 200
    execute_body = execute_response.json()
    assert execute_body["success"] is True
    execution_data = execute_body["data"]

    settings = get_settings()
    splits_dir = settings.paths.projects_dir / project_id / "splits"
    assert splits_dir.exists()

    for segment, filename in zip(preview_segments, execution_data["written_files"], strict=True):
        segment_path = splits_dir / filename
        assert segment_path.exists()
        expected_text = text[segment["start_offset"] : segment["end_offset"]]
        assert segment_path.read_text(encoding="utf-8") == expected_text

    metadata_path = splits_dir / "metadata.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["strategy"] == "fixed_count"
    assert metadata["files"] == execution_data["written_files"]
    assert len(metadata["segments"]) == len(preview_segments)


def test_execute_requires_overwrite_when_outputs_exist(client: TestClient) -> None:
    project_id = "overwrite"
    text = "a" * 20
    payload = {
        "project_id": project_id,
        "text": text,
        "strategy": "character_count",
        "parameters": {"max_characters": 5},
    }

    first_response = client.post("/splitter/execute", json={**payload, "overwrite": False})
    assert first_response.status_code == 200
    assert first_response.json()["success"] is True

    second_response = client.post("/splitter/execute", json=payload)
    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["success"] is False
    assert second_body["error"]["code"] == "splitter.execution_failure"

    overwrite_response = client.post("/splitter/execute", json={**payload, "overwrite": True})
    assert overwrite_response.status_code == 200
    assert overwrite_response.json()["success"] is True


def test_ratio_strategy_respects_relative_lengths(client: TestClient) -> None:
    text = "abcdefghij"
    payload = {
        "project_id": "ratio",
        "text": text,
        "strategy": "ratio",
        "parameters": {"ratios": [2, 1]},
    }

    response = client.post("/splitter/preview", json=payload)
    assert response.status_code == 200
    data = response.json()["data"]
    segments = data["segments"]
    assert len(segments) == 2
    assert segments[0]["character_count"] >= segments[1]["character_count"]
    total_chars = sum(segment["character_count"] for segment in segments)
    assert total_chars == len(text)

