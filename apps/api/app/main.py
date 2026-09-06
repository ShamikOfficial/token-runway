"""
TokenRunway API — Stage 1: fuel ingest + runway readout.

Talks to DynamoDB/S3 on Floci when AWS_ENDPOINT_URL is set.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import budgets, health, usage

UI_DIR = Path(__file__).resolve().parents[2] / "ui" / "public"

app = FastAPI(
    title="TokenRunway",
    description="LLM fuel planner — Stage 1 runway & usage ingest (Floci / AWS).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(budgets.router, prefix="/v1")
app.include_router(usage.router, prefix="/v1")


@app.get("/")
def dashboard():
    index = UI_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "service": "TokenRunway",
        "stage": 1,
        "docs": "/docs",
        "hint": "UI not found — open /docs for the API.",
    }


if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
