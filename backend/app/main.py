from typing import Dict

from fastapi import FastAPI

app = FastAPI(title="项目后端", version="0.1.0")


@app.get("/healthz", tags=["Health"], summary="健康检查")
async def health_check() -> Dict[str, str]:
    """健康检查接口，返回服务当前状态。"""
    return {"status": "ok"}
