from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, root_validator, validator

from ..services import (
    SplitStrategy,
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


def resolve_projects_root() -> Path:
    env_value = os.getenv(PROJECTS_ROOT_ENV)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / PROJECTS_DIR_NAME


def validate_project_name(name: str) -> str:
    candidate = name.strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    if not PROJECT_NAME_PATTERN.match(candidate):
        raise HTTPException(status_code=400, detail="项目名称包含非法字符")
    return candidate


def ensure_project_directory(project_name: str) -> Path:
    root = resolve_projects_root()
    directory = root / project_name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_project_directory(project_name: str) -> Path:
    root = resolve_projects_root()
    directory = root / project_name
    return directory


@router.post("/{project_name}/upload", response_model=UploadResponse, summary="上传项目源文件")
async def upload_project_file(project_name: str, file: UploadFile = File(...)) -> UploadResponse:
    validated_project = validate_project_name(project_name)

    if file.filename is None or not file.filename.strip():
        raise HTTPException(status_code=400, detail="上传文件缺少文件名")

    safe_filename = Path(file.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="无法解析有效的文件名")

    project_dir = ensure_project_directory(validated_project)
    destination = project_dir / safe_filename

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

    file_path = project_dir / safe_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="指定文件不存在")

    try:
        raw_bytes = file_path.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {exc}")

    try:
        text = raw_bytes.decode(payload.normalized_encoding())
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="无法使用提供的编码解码文件内容")

    strategy = payload.strategy

    try:
        if strategy == SplitStrategy.CHARACTER_COUNT:
            segments = split_by_character_count(text, payload.max_chars or 0)
        elif strategy == SplitStrategy.KEYWORDS:
            segments = split_by_keywords(text, payload.keywords or [])
        elif strategy == SplitStrategy.RATIO:
            segments = split_by_ratio(text, payload.ratios or [])
        elif strategy == SplitStrategy.FIXED_CHAPTERS:
            segments = split_by_fixed_chapters(text, payload.chapters or 0)
        else:
            raise HTTPException(status_code=400, detail="不支持的分割策略")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    encoding = payload.normalized_encoding()
    total_characters = len(text)
    total_bytes = len(raw_bytes)

    segment_previews: List[SegmentPreview] = []
    cursor = 0

    for index, segment_text in enumerate(segments, start=1):
        character_count = len(segment_text)
        byte_length = len(segment_text.encode(encoding))
        segment_preview = SegmentPreview(
            index=index,
            text=segment_text,
            character_count=character_count,
            byte_length=byte_length,
            start_offset=cursor,
            end_offset=cursor + character_count,
        )
        cursor += character_count
        segment_previews.append(segment_preview)

    return SplitPreviewResponse(
        project=validated_project,
        filename=safe_filename,
        strategy=strategy,
        encoding=encoding,
        segment_count=len(segment_previews),
        total_characters=total_characters,
        total_bytes=total_bytes,
        segments=segment_previews,
    )
