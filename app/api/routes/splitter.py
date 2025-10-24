"""Routes exposing text splitting preview and execution."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...core.settings import Settings, get_settings
from ...core.splitter.exceptions import SplitterError
from ...core.splitter.service import SplitPreviewResult, SplitterService
from ...models.common import ResponseEnvelope
from ...models.splitter import (
    SegmentPreview,
    SplitExecuteRequest,
    SplitExecutionResponse,
    SplitPreviewResponse,
    SplitRequest,
)

router = APIRouter(prefix="/splitter", tags=["splitter"])


def get_splitter_service(settings: Settings = Depends(get_settings)) -> SplitterService:
    return SplitterService(settings)


def _preview_response_from(result: SplitPreviewResult) -> SplitPreviewResponse:
    segments = [
        SegmentPreview(
            index=segment.index,
            start_offset=segment.start_offset,
            end_offset=segment.end_offset,
            byte_start_offset=segment.byte_start_offset,
            byte_end_offset=segment.byte_end_offset,
            character_count=segment.character_count,
            byte_count=segment.byte_count,
        )
        for segment in result.segments
    ]
    return SplitPreviewResponse(
        project_id=result.project_id,
        strategy=result.strategy,
        parameters=result.parameters,
        total_segments=len(segments),
        total_characters=result.total_characters,
        total_bytes=result.total_bytes,
        source_sha256=result.source_sha256,
        segments=segments,
    )


@router.post("/preview", response_model=ResponseEnvelope[SplitPreviewResponse], summary="Preview splitting without persisting files")
async def preview_split(
    request: SplitRequest, service: SplitterService = Depends(get_splitter_service)
) -> ResponseEnvelope[SplitPreviewResponse]:
    try:
        result = service.preview(
            project_id=request.project_id,
            text=request.text,
            strategy=request.strategy,
            parameters=request.parameters,
        )
    except SplitterError as exc:
        return ResponseEnvelope.error_payload(exc.code, str(exc), exc.details)

    payload = _preview_response_from(result)
    return ResponseEnvelope.success_payload(payload)


@router.post("/execute", response_model=ResponseEnvelope[SplitExecutionResponse], summary="Execute splitting and persist files")
async def execute_split(
    request: SplitExecuteRequest, service: SplitterService = Depends(get_splitter_service)
) -> ResponseEnvelope[SplitExecutionResponse]:
    try:
        execution = service.execute(
            project_id=request.project_id,
            text=request.text,
            strategy=request.strategy,
            parameters=request.parameters,
            overwrite=request.overwrite,
        )
    except SplitterError as exc:
        return ResponseEnvelope.error_payload(exc.code, str(exc), exc.details)

    preview_payload = _preview_response_from(execution.preview)
    response = SplitExecutionResponse(
        **preview_payload.model_dump(),
        output_directory=str(execution.output_directory),
        metadata_path=str(execution.metadata_path),
        written_files=execution.written_files,
    )
    return ResponseEnvelope.success_payload(response)


__all__ = ("router",)
