"""
TokenRunway API — flight control on Floci / AWS.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import budgets, flight_ops, flights, forecast, health, tower, usage, weather

UI_DIR = Path(__file__).resolve().parents[2] / "ui" / "public"

app = FastAPI(
    title="TokenRunway",
    description="LLM flight control — runway, landing, Tailwind/Headwind weather (Floci / AWS).",
    version="0.4.0",
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
app.include_router(flights.router, prefix="/v1")
app.include_router(flight_ops.router, prefix="/v1")
app.include_router(forecast.router, prefix="/v1")
app.include_router(tower.router, prefix="/v1")
app.include_router(weather.router, prefix="/v1")


@app.get("/")
def dashboard():
    index = UI_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "TokenRunway", "stage": 4, "docs": "/docs"}


if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
