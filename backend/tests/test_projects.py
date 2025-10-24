import json
from pathlib import Path
from typing import List

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.projects import resolve_projects_root


@pytest.fixture
def projects_environment(monkeypatch, tmp_path):
    root = tmp_path / "projects_root"
    monkeypatch.setenv("PROJECTS_ROOT", str(root))
    return root


@pytest.fixture
def client(projects_environment):
    with TestClient(app) as test_client:
        yield test_client


def test_upload_project_file_saves_content(client, projects_environment):
    project_name = "测试小说"
    file_content = "第一章内容\n第二章内容".encode("utf-8")

    response = client.post(
        f"/projects/{project_name}/upload",
        files={"file": ("novel.txt", file_content, "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project"] == project_name
    assert data["filename"] == "novel.txt"
    assert data["size"] == len(file_content)

    saved_file = projects_environment / project_name / "novel.txt"
    assert saved_file.exists()
    assert saved_file.read_bytes() == file_content


def test_split_preview_character_count_strategy(client, projects_environment):
    project_name = "字符策略"
    filename = "story.txt"
    text_content = "第一段内容ABC第二段"
    max_chars = 4

    project_dir = projects_environment / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / filename
    project_file.write_bytes(text_content.encode("utf-8"))

    response = client.post(
        f"/projects/{project_name}/split-preview",
        json={
            "filename": filename,
            "strategy": "character_count",
            "max_chars": max_chars,
            "encoding": "utf-8",
        },
    )

    assert response.status_code == 200
    data = response.json()

    expected_segments: List[str] = [
        text_content[index : index + max_chars] for index in range(0, len(text_content), max_chars)
    ]

    assert data["segment_count"] == len(expected_segments)
    assert data["total_characters"] == len(text_content)
    assert data["total_bytes"] == len(text_content.encode("utf-8"))

    cursor = 0
    for index, expected_text in enumerate(expected_segments):
        segment = data["segments"][index]
        assert segment["text"] == expected_text
        assert segment["character_count"] == len(expected_text)
        assert segment["byte_length"] == len(expected_text.encode("utf-8"))
        assert segment["start_offset"] == cursor
        cursor += len(expected_text)
        assert segment["end_offset"] == cursor

    assert cursor == len(text_content)


def test_split_preview_keywords_strategy(client, projects_environment):
    project_name = "关键词策略"
    filename = "novel.txt"
    text_content = (
        "第一章\n这是第一章内容。\n"
        "第二章\n这是第二章内容。\n"
        "第三章\n这是第三章内容。"
    )
    keywords = ["第二章", "第三章"]

    project_dir = projects_environment / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / filename
    project_file.write_bytes(text_content.encode("utf-8"))

    response = client.post(
        f"/projects/{project_name}/split-preview",
        json={
            "filename": filename,
            "strategy": "keywords",
            "keywords": keywords,
            "encoding": "utf-8",
        },
    )

    assert response.status_code == 200
    data = response.json()

    first_keyword = text_content.index(keywords[0])
    second_keyword = text_content.index(keywords[1])
    expected_segments = [
        text_content[:first_keyword],
        text_content[first_keyword:second_keyword],
        text_content[second_keyword:],
    ]

    assert data["segment_count"] == len(expected_segments)
    assert data["total_characters"] == len(text_content)

    for index, expected_text in enumerate(expected_segments):
        segment = data["segments"][index]
        assert segment["text"] == expected_text
        assert segment["character_count"] == len(expected_text)
        assert segment["byte_length"] == len(expected_text.encode("utf-8"))

    assert sum(segment["byte_length"] for segment in data["segments"]) == len(
        text_content.encode("utf-8")
    )


def test_split_preview_ratio_strategy(client, projects_environment):
    project_name = "比例策略"
    filename = "ratio.txt"
    text_content = "ABCDEFGHIJKL"
    ratios = [1, 1, 2]

    project_dir = projects_environment / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / filename
    project_file.write_text(text_content, encoding="utf-8")

    response = client.post(
        f"/projects/{project_name}/split-preview",
        json={
            "filename": filename,
            "strategy": "ratio",
            "ratios": ratios,
            "encoding": "utf-8",
        },
    )

    assert response.status_code == 200
    data = response.json()

    expected_segments = [text_content[:3], text_content[3:6], text_content[6:]]

    assert data["segment_count"] == len(expected_segments)
    assert [segment["text"] for segment in data["segments"]] == expected_segments
    assert sum(segment["character_count"] for segment in data["segments"]) == len(text_content)
    assert sum(segment["byte_length"] for segment in data["segments"]) == len(
        text_content.encode("utf-8")
    )


def test_split_preview_fixed_chapters_strategy(client, projects_environment):
    project_name = "固定章节"
    filename = "short.txt"
    text_content = "短文"
    chapters = 4

    project_dir = projects_environment / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / filename).write_text(text_content, encoding="utf-8")

    response = client.post(
        f"/projects/{project_name}/split-preview",
        json={
            "filename": filename,
            "strategy": "fixed_chapters",
            "chapters": chapters,
            "encoding": "utf-8",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["segment_count"] == chapters
    segments = data["segments"]
    assert segments[0]["text"] == text_content[0:1]
    assert segments[1]["text"] == text_content[1:2]
    assert segments[2]["text"] == ""
    assert segments[3]["text"] == ""
    assert sum(segment["character_count"] for segment in segments) == len(text_content)


def test_split_process_generates_markdown_reports(client, projects_environment, monkeypatch):
    project_name = "管线项目"
    filename = "novel.txt"
    text_content = "第一章内容\n第二章内容"

    project_dir = projects_environment / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / filename).write_text(text_content, encoding="utf-8")

    ai_calls: List[tuple[int, str]] = []

    def fake_invoke_ai_response(*, ai_config, segment_text, segment_index):
        ai_calls.append((segment_index, segment_text))
        return f"AI 输出 {segment_index}: {segment_text[:5]}"

    monkeypatch.setattr(
        "app.services.pipeline.invoke_ai_response",
        fake_invoke_ai_response,
    )

    response = client.post(
        f"/projects/{project_name}/split-process",
        json={
            "filename": filename,
            "strategy": "character_count",
            "max_chars": 5,
            "encoding": "utf-8",
            "report_name": "报告 v1",
            "ai": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "system_prompts": [{"text": "汇总", "priority": 1}],
                "options": {"temperature": 0.2},
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project"] == project_name
    assert data["report_dir"].startswith("reports/")
    assert data["report_name"] == "报告_v1"
    assert len(ai_calls) == data["segment_count"] == len(data["segments"])

    metadata_path = projects_environment / project_name / data["metadata_path"]
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["ai"]["provider"] == "openai"
    assert metadata["report_name"] == data["report_name"]

    first_segment_path = projects_environment / project_name / data["segments"][0]["markdown_path"]
    assert first_segment_path.exists()
    first_segment_content = first_segment_path.read_text(encoding="utf-8")
    assert "AI 输出 1" in first_segment_content
    assert "### Original Segment" in first_segment_content

    report_path = projects_environment / project_name / data["report_path"]
    assert report_path.exists()

    final_path = projects_environment / project_name / data["final_report_path"]
    assert final_path.exists()
    assert "Final Report" in final_path.read_text(encoding="utf-8")


def test_retry_segment_updates_markdown_without_final_merge(client, projects_environment, monkeypatch):
    project_name = "重试项目"
    filename = "story.txt"
    text_content = "第一段内容第二段内容第三段"

    project_dir = projects_environment / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / filename).write_text(text_content, encoding="utf-8")

    def initial_ai(*, ai_config, segment_text, segment_index):
        return f"初始 {segment_index}"

    monkeypatch.setattr("app.services.pipeline.invoke_ai_response", initial_ai)

    initial_response = client.post(
        f"/projects/{project_name}/split-process",
        json={
            "filename": filename,
            "strategy": "character_count",
            "max_chars": 3,
            "encoding": "utf-8",
            "ai": {
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        },
    )
    assert initial_response.status_code == 200
    initial_data = initial_response.json()

    retry_calls: List[int] = []

    def retry_ai(*, ai_config, segment_text, segment_index):
        retry_calls.append(segment_index)
        return f"重试 {segment_index}: {segment_text[-3:]}"

    monkeypatch.setattr("app.services.pipeline.invoke_ai_response", retry_ai)

    retry_response = client.post(
        f"/projects/{project_name}/reports/{initial_data['report_name']}/segments/2/retry",
        json={
            "cascade_integrate": True,
            "final_merge": False,
            "ai": {
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        },
    )

    assert retry_response.status_code == 200
    retry_data = retry_response.json()
    assert retry_data["report_path"] is not None
    assert retry_data["final_report_path"] is None
    assert retry_calls == [2]

    updated_segment_path = projects_environment / project_name / retry_data["segment"]["markdown_path"]
    assert "重试 2" in updated_segment_path.read_text(encoding="utf-8")

    report_path = projects_environment / project_name / retry_data["report_path"]
    assert "重试 2" in report_path.read_text(encoding="utf-8")

    metadata_path = projects_environment / project_name / retry_data["metadata_path"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["ai"]["model"] == "gpt-4o-mini"


def test_resolve_projects_root_defaults_to_app_data(monkeypatch):
    monkeypatch.delenv("PROJECTS_ROOT", raising=False)
    assert resolve_projects_root() == Path("/app/data/projects")
