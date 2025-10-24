from pathlib import Path

from app.agents import (
    DEFAULT_AGENTS_VERSION,
    ensure_agents_file_exists,
    load_agents_document,
)


def test_ensure_creates_default_agents_file_when_missing(tmp_path: Path) -> None:
    target_path = tmp_path / "agents.md"

    ensure_agents_file_exists(target_path)

    assert target_path.exists()
    content = target_path.read_text(encoding="utf-8")
    assert "Agents 配置示例" in content
    assert DEFAULT_AGENTS_VERSION in content
    assert "合并策略示例" in content


def test_load_agents_document_reads_latest_content(tmp_path: Path) -> None:
    target_path = tmp_path / "agents.md"

    ensure_agents_file_exists(target_path)
    first_content = load_agents_document(target_path)

    updated_content = "custom content"
    target_path.write_text(updated_content, encoding="utf-8")

    assert load_agents_document(target_path) == updated_content
    assert first_content != updated_content


def test_load_agents_document_regenerates_after_deletion(tmp_path: Path) -> None:
    target_path = tmp_path / "agents.md"

    ensure_agents_file_exists(target_path)
    target_path.unlink()

    regenerated_content = load_agents_document(target_path)

    assert target_path.exists()
    assert regenerated_content == target_path.read_text(encoding="utf-8")
    assert DEFAULT_AGENTS_VERSION in regenerated_content
    assert "合并策略示例" in regenerated_content
