from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, root_validator, validator

from ..services import (
    AIInvokeConfig,
    PipelineError,
    PromptDefinitionData,
    SegmentInput,
    SplitStrategy,
    process_segments,
    retry_segment,
    split_by_character_count,
    split_by_fixed_chapters,
    split_by_keywords,
    split_by_ratio,
)

PROJECTS_DIR_NAME = "projects"
PROJECTS_ROOT_ENV = "PROJECTS_ROOT"
PROJECT_NAME_PATTERN = re.compile(r"^[\w\-.\s\u4e00-\u9fff]+$")
DEFAULT_ENCODING = "utf-8"
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB

router = APIRouter(prefix="/projects", tags=["Projects"])


class UploadResponse(BaseModel):
    project: str
    filename: str
    size: int = Field(..., ge=0)


class SegmentPreview(BaseModel):
    index: int = Field(..., ge=1)
    text: str
    character_count: int = Field(..., ge=0)
    byte_length: int = Field(..., ge=0)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)


class SplitPreviewResponse(BaseModel):
    project: str
    filename: str
    strategy: SplitStrategy
    encoding: str
    segment_count: int = Field(..., ge=0)
    total_characters: int = Field(..., ge=0)
    total_bytes: int = Field(..., ge=0)
    segments: List[SegmentPreview]


class SplitPreviewRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    strategy: SplitStrategy
    max_chars: Optional[int] = Field(None, gt=0)
    keywords: Optional[List[str]] = None
    ratios: Optional[List[float]] = None
    chapters: Optional[int] = Field(None, gt=0)
    encoding: str = Field(DEFAULT_ENCODING, min_length=1)

    @validator("keywords", pre=True)
    def ensure_keywords_list(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        if not isinstance(value, list) or not value:
            raise ValueError("keywords must be a non-empty list of strings")

        cleaned_keywords: List[str] = []
        for keyword in value:
            if not isinstance(keyword, str):
                raise ValueError("keywords must be a non-empty list of strings")
            trimmed = keyword.strip()
            if not trimmed:
                raise ValueError("keywords must be a non-empty list of strings")
            cleaned_keywords.append(trimmed)

        return cleaned_keywords

    @validator("ratios", pre=True)
    def ensure_ratios_list(cls, value: Optional[List[float]]) -> Optional[List[float]]:
        if value is None:
            return None
        if not isinstance(value, list) or not value:
            raise ValueError("ratios must be a non-empty list")
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            raise ValueError("ratios must contain numeric values")

    @validator("encoding")
    def normalize_encoding(cls, value: str) -> str:
        encoding = value.strip()
        if not encoding:
            raise ValueError("encoding must not be empty")
        return encoding

    @root_validator
    def validate_strategy_options(cls, values: dict) -> dict:
        strategy = values.get("strategy")
        if strategy == SplitStrategy.CHARACTER_COUNT:
            if values.get("max_chars") is None:
                raise ValueError("max_chars is required for character_count strategy")
        elif strategy == SplitStrategy.KEYWORDS:
            if not values.get("keywords"):
                raise ValueError("keywords are required for keywords strategy")
        elif strategy == SplitStrategy.RATIO:
            ratios = values.get("ratios")
            if not ratios:
                raise ValueError("ratios are required for ratio strategy")
            if any(ratio <= 0 for ratio in ratios):
                raise ValueError("ratios must contain positive numbers")
        elif strategy == SplitStrategy.FIXED_CHAPTERS:
            if values.get("chapters") is None:
                raise ValueError("chapters is required for fixed_chapters strategy")
        return values

    def normalized_encoding(self) -> str:
        return self.encoding or DEFAULT_ENCODING


class PromptDefinitionModel(BaseModel):
    text: str = Field(..., min_length=1)
    priority: int = 0


class AIConfigModel(BaseModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    system_prompts: List[PromptDefinitionModel] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)

    def to_service_config(self) -> AIInvokeConfig:
        return AIInvokeConfig(
            provider=self.provider,
            model=self.model,
            system_prompts=[
                PromptDefinitionData(text=item.text, priority=item.priority)
                for item in self.system_prompts
            ],
            options=self.options,
        )


class SegmentReportInfo(BaseModel):
    index: int = Field(..., ge=1)
    markdown_path: str = Field(..., min_length=1)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    character_count: int = Field(..., ge=0)
    byte_length: int = Field(..., ge=0)


class SplitProcessRequest(SplitPreviewRequest):
    ai: AIConfigModel
    report_name: Optional[str] = Field(None, min_length=1)
    cascade_integrate: bool = True
    final_merge: bool = True


class SplitProcessResponse(BaseModel):
    project: str
    filename: str
    report_name: str
    report_dir: str
    metadata_path: str
    segment_count: int = Field(..., ge=0)
    total_characters: int = Field(..., ge=0)
    total_bytes: int = Field(..., ge=0)
    report_path: Optional[str]
    final_report_path: Optional[str]
    segments: List[SegmentReportInfo]


class SegmentRetryRequest(BaseModel):
    ai: Optional[AIConfigModel] = None
    cascade_integrate: bool = True
    final_merge: bool = True
    encoding: Optional[str] = None

    @validator("encoding")
    def normalize_optional_encoding(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("encoding must not be empty")
        return trimmed


class SegmentRetryResponse(BaseModel):
    project: str
    report_name: str
    segment: SegmentReportInfo
    metadata_path: str
    report_path: Optional[str]
    final_report_path: Optional[str]


def resolve_projects_root() -> Path:
    env_value = os.getenv(PROJECTS_ROOT_ENV)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path("/app/data") / PROJECTS_DIR_NAME


def validate_project_name(name: str) -> str:
    candidate = name.strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    if not PROJECT_NAME_PATTERN.match(candidate):
        raise HTTPException(status_code=400, detail="项目名称包含非法字符")
    return candidate


def ensure_project_directory(project_name: str) -> Path:
    root = resolve_projects_root()
    directory = (root / project_name).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_project_directory(project_name: str) -> Path:
    root = resolve_projects_root()
    return (root / project_name).resolve()


def resolve_project_file_path(project_dir: Path, filename: str) -> Path:
    candidate = (project_dir / filename).resolve()
    project_root = project_dir.resolve()
    if not candidate.is_relative_to(project_root):
        raise HTTPException(status_code=400, detail="非法的文件路径")
    return candidate


def _project_relative_path(project_dir: Path, target: Path) -> str:
    try:
        relative = target.resolve().relative_to(project_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="生成文件路径超出项目目录") from exc
    return relative.as_posix()


def _load_project_text(project_dir: Path, filename: str, encoding: str) -> tuple[str, bytes, Path]:
    file_path = resolve_project_file_path(project_dir, filename)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="指定文件不存在")

    try:
        raw_bytes = file_path.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {exc}")

    try:
        text = raw_bytes.decode(encoding)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="无法使用提供的编码解码文件内容")

    return text, raw_bytes, file_path


def _execute_split(text: str, payload: SplitPreviewRequest) -> List[str]:
    strategy = payload.strategy
    try:
        if strategy == SplitStrategy.CHARACTER_COUNT:
            return split_by_character_count(text, payload.max_chars or 0)
        if strategy == SplitStrategy.KEYWORDS:
            return split_by_keywords(text, payload.keywords or [])
        if strategy == SplitStrategy.RATIO:
            return split_by_ratio(text, payload.ratios or [])
        if strategy == SplitStrategy.FIXED_CHAPTERS:
            return split_by_fixed_chapters(text, payload.chapters or 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raise HTTPException(status_code=400, detail="不支持的分割策略")


def _build_segment_previews(
    segments: Sequence[str],
    *,
    encoding: str,
) -> List[SegmentPreview]:
    previews: List[SegmentPreview] = []
    cursor = 0

    for index, segment_text in enumerate(segments, start=1):
        character_count = len(segment_text)
        byte_length = len(segment_text.encode(encoding))
        preview = SegmentPreview(
            index=index,
            text=segment_text,
            character_count=character_count,
            byte_length=byte_length,
            start_offset=cursor,
            end_offset=cursor + character_count,
        )
        cursor += character_count
        previews.append(preview)

    return previews


@router.post("/{project_name}/upload", response_model=UploadResponse, summary="上传项目源文件")
async def upload_project_file(project_name: str, file: UploadFile = File(...)) -> UploadResponse:
    validated_project = validate_project_name(project_name)

    if file.filename is None or not file.filename.strip():
        raise HTTPException(status_code=400, detail="上传文件缺少文件名")

    safe_filename = Path(file.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="无法解析有效的文件名")

    project_dir = ensure_project_directory(validated_project)
    destination = resolve_project_file_path(project_dir, safe_filename)

    total_written = 0
    try:
        with destination.open("wb") as buffer:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                buffer.write(chunk)
                total_written += len(chunk)
    finally:
        await file.close()

    return UploadResponse(project=validated_project, filename=safe_filename, size=total_written)


@router.post(
    "/{project_name}/split-preview",
    response_model=SplitPreviewResponse,
    summary="预览分割策略结果",
)
async def preview_split(project_name: str, payload: SplitPreviewRequest) -> SplitPreviewResponse:
    validated_project = validate_project_name(project_name)
    project_dir = get_project_directory(validated_project)

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")

    safe_filename = Path(payload.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="无法解析有效的文件名")

    encoding = payload.normalized_encoding()
    text, raw_bytes, _ = _load_project_text(project_dir, safe_filename, encoding)

    segments = _execute_split(text, payload)
    segment_previews = _build_segment_previews(segments, encoding=encoding)

    return SplitPreviewResponse(
        project=validated_project,
        filename=safe_filename,
        strategy=payload.strategy,
        encoding=encoding,
        segment_count=len(segment_previews),
        total_characters=len(text),
        total_bytes=len(raw_bytes),
        segments=segment_previews,
    )


@router.post(
    "/{project_name}/split-process",
    response_model=SplitProcessResponse,
    summary="执行分割并生成 Markdown 报告",
)
async def process_split(project_name: str, payload: SplitProcessRequest) -> SplitProcessResponse:
    validated_project = validate_project_name(project_name)
    project_dir = get_project_directory(validated_project)

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")

    safe_filename = Path(payload.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="无法解析有效的文件名")

    encoding = payload.normalized_encoding()
    text, raw_bytes, _ = _load_project_text(project_dir, safe_filename, encoding)

    segments = _execute_split(text, payload)
    segment_previews = _build_segment_previews(segments, encoding=encoding)

    segment_inputs = [
        SegmentInput(
            index=preview.index,
            text=preview.text,
            start_offset=preview.start_offset,
            end_offset=preview.end_offset,
            byte_length=preview.byte_length,
            character_count=preview.character_count,
        )
        for preview in segment_previews
    ]

    ai_config = payload.ai.to_service_config()

    try:
        result = process_segments(
            project_dir=project_dir,
            source_filename=safe_filename,
            encoding=encoding,
            strategy=payload.strategy,
            segments=segment_inputs,
            ai_config=ai_config,
            report_name=payload.report_name,
            cascade_integrate=payload.cascade_integrate,
            final_merge=payload.final_merge,
        )
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    segments_info = [
        SegmentReportInfo(
            index=summary.index,
            markdown_path=_project_relative_path(project_dir, summary.markdown_path),
            start_offset=summary.start_offset,
            end_offset=summary.end_offset,
            character_count=summary.character_count,
            byte_length=summary.byte_length,
        )
        for summary in result.segments
    ]

    return SplitProcessResponse(
        project=validated_project,
        filename=safe_filename,
        report_name=result.report_name,
        report_dir=_project_relative_path(project_dir, result.report_dir),
        metadata_path=_project_relative_path(project_dir, result.metadata_path),
        segment_count=len(segment_inputs),
        total_characters=len(text),
        total_bytes=len(raw_bytes),
        report_path=(
            _project_relative_path(project_dir, result.report_path)
            if result.report_path is not None
            else None
        ),
        final_report_path=(
            _project_relative_path(project_dir, result.final_report_path)
            if result.final_report_path is not None
            else None
        ),
        segments=segments_info,
    )


@router.post(
    "/{project_name}/reports/{report_name}/segments/{segment_index}/retry",
    response_model=SegmentRetryResponse,
    summary="重试单个分割段的 Markdown 生成",
)
async def retry_split_segment(
    project_name: str,
    report_name: str,
    segment_index: int,
    payload: SegmentRetryRequest,
) -> SegmentRetryResponse:
    if segment_index < 1:
        raise HTTPException(status_code=400, detail="segment_index 必须大于等于 1")

    validated_project = validate_project_name(project_name)
    project_dir = get_project_directory(validated_project)

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")

    ai_config = payload.ai.to_service_config() if payload.ai else None

    try:
        result = retry_segment(
            project_dir=project_dir,
            report_name=report_name,
            segment_index=segment_index,
            encoding_override=payload.encoding,
            ai_config=ai_config,
            cascade_integrate=payload.cascade_integrate,
            final_merge=payload.final_merge,
        )
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    segment_info = SegmentReportInfo(
        index=result.segment.index,
        markdown_path=_project_relative_path(project_dir, result.segment.markdown_path),
        start_offset=result.segment.start_offset,
        end_offset=result.segment.end_offset,
        character_count=result.segment.character_count,
        byte_length=result.segment.byte_length,
    )

    return SegmentRetryResponse(
        project=validated_project,
        report_name=result.report_name,
        segment=segment_info,
        metadata_path=_project_relative_path(project_dir, result.metadata_path),
        report_path=(
            _project_relative_path(project_dir, result.report_path)
            if result.report_path is not None
            else None
        ),
        final_report_path=(
            _project_relative_path(project_dir, result.final_report_path)
            if result.final_report_path is not None
            else None
        ),
    )
