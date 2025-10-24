import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Example API")

STATIC_ROOT = Path(
    os.getenv("STATIC_ROOT", Path(__file__).resolve().parent / "static")
)
if STATIC_ROOT.exists():
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


@app.get("/health", tags=["internal"])
async def health() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the frontend index page when available."""
    index_file = STATIC_ROOT / "index.html"
    if STATIC_ROOT.exists() and index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>API is running</h1>")
