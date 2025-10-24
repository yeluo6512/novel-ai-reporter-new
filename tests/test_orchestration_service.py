from __future__ import annotations

from pathlib import Path

import pytest

from app.core.settings import Settings
from app.core.agents import AgentsService
from app.models.orchestration import TaskState
from app.services.orchestration import OrchestrationService


@pytest.fixture()
def sample_manifest() -> str:
    return (
        "# Agents Manifest\n"
        "\n"
        "## analysis\n"
        "Summarise the segment with key facts.\n"
        "\n"
        "## integration\n"
        "Integrate consecutive segments highlighting continuity.\n"
        "\n"
        "## finalization\n"
        "Combine all integration outputs in chronological order.\n"
    )


@pytest.fixture()
def prepared_service(tmp_path: Path, sample_manifest: str) -> OrchestrationService:
    settings = Settings(  # type: ignore[call-arg]
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
    )
    settings.ensure_directories()
    manifest_path = settings.agents_manifest_path
    manifest_path.write_text(sample_manifest, encoding="utf-8")

    agents_service = AgentsService(settings=settings)
    agents_service.invalidate_cache()

    service = OrchestrationService(settings=settings, agents_service=agents_service)

    project_dir = settings.paths.projects_dir / "project-alpha"
    splits_dir = project_dir / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    (splits_dir / "0.txt").write_text("First split content for analysis.", encoding="utf-8")
    (splits_dir / "1.txt").write_text("Second split content continues narrative.", encoding="utf-8")
    (splits_dir / "2.txt").write_text("Third split concludes the overview.", encoding="utf-8")

    return service


def test_full_pipeline_generates_reports(prepared_service: OrchestrationService) -> None:
    status = prepared_service.generate_reports("project-alpha")
    assert status.status == TaskState.COMPLETED

    settings = prepared_service.settings
    project_dir = settings.paths.projects_dir / "project-alpha"
    splits_dir = project_dir / "splits"
    integrations_dir = project_dir / "integrations"
    final_report_path = project_dir / "final_report.md"

    for index in (0, 1, 2):
        analysis_path = splits_dir / f"{index}.md"
        assert analysis_path.exists()
        text = analysis_path.read_text(encoding="utf-8")
        assert f"Segment {index} Analysis" in text

    integrated_path = integrations_dir / "integrated_0.md"
    assert integrated_path.exists()
    assert "Integrated Report 0" in integrated_path.read_text(encoding="utf-8")
    # Only three segments, so no second integration file should remain.
    assert not (integrations_dir / "integrated_1.md").exists()

    final_content = final_report_path.read_text(encoding="utf-8")
    assert "Final Report" in final_content
    assert "Integrated Summary 1" in final_content


def test_regeneration_updates_target_segments(prepared_service: OrchestrationService) -> None:
    project_id = "project-alpha"
    settings = prepared_service.settings
    project_dir = settings.paths.projects_dir / project_id
    splits_dir = project_dir / "splits"
    integrations_dir = project_dir / "integrations"

    prepared_service.generate_reports(project_id)

    analysis_path = splits_dir / "1.md"
    integration_path = integrations_dir / "integrated_0.md"
    original_analysis = analysis_path.read_text(encoding="utf-8")
    original_integration = integration_path.read_text(encoding="utf-8")

    # Update a single segment and trigger regeneration for that index only.
    (splits_dir / "1.txt").write_text("Second split updated with new context and insights.", encoding="utf-8")

    prepared_service.generate_reports(project_id, regenerate_segments=[1], cascade=True)

    refreshed_analysis = analysis_path.read_text(encoding="utf-8")
    refreshed_integration = integration_path.read_text(encoding="utf-8")

    assert refreshed_analysis != original_analysis
    assert refreshed_integration != original_integration

    status = prepared_service.get_status(project_id)
    assert status.status == TaskState.COMPLETED
    assert status.requested_segments == [1]
    assert status.cascade is True
