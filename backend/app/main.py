from typing import Dict

from fastapi import FastAPI

from .agents import ensure_agents_file_exists, load_agents_document
from .routers import projects_router

app = FastAPI(title="项目后端", version="0.1.0")
app.include_router(projects_router)


@app.on_event("startup")
async def bootstrap_agents_file() -> None:
    """检测并初始化 agents.md 文件。"""
    ensure_agents_file_exists()


@app.get("/healthz", tags=["Health"], summary="健康检查")
async def health_check() -> Dict[str, str]:
    """健康检查接口，返回服务当前状态。"""
    return {"status": "ok"}


@app.get("/agents", tags=["Agents"], summary="读取 agents.md 当前配置")
async def get_agents_document() -> Dict[str, str]:
    """返回 agents.md 文件的最新内容。"""
    return {"content": load_agents_document()}
