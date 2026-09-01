"""
FastAPI application for Railway Block Planner.

Exposes REST APIs for interacting with persistent unified railway data.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api.routes import blocks, maintenance, plans, trains
from backend.app.database.connection import SessionLocal, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager: initializes database on startup."""
    init_db()
    yield


app = FastAPI(
    title="Railway Block Planner API",
    description=(
        "Centralized railway maintenance block planning backend exposing "
        "persisted unified operational entities across trains, maintenance requests, "
        "movements, and blocks."
    ),
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
allowed_origins_raw = os.getenv("CORS_ORIGINS", "*")
allowed_origins = [orig.strip() for orig in allowed_origins_raw.split(",") if orig.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health & Status Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", summary="Health check endpoint", tags=["System"])
def health_check() -> Dict[str, Any]:
    """Check API and database connectivity."""
    db_status = "connected"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "version": "0.3.0",
        "phase": "Phase 3 - Database + Repositories + FastAPI",
    }


@app.get("/", summary="Root index", tags=["System"])
def root() -> Dict[str, Any]:
    """Root metadata response."""
    return {
        "name": "Railway Block Planner API",
        "version": "0.3.0",
        "docs": "/docs",
        "health": "/health",
        "phase": "Phase 3",
    }


# ---------------------------------------------------------------------------
# Route Registrations
# ---------------------------------------------------------------------------
app.include_router(trains.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(blocks.router, prefix="/api")
app.include_router(plans.router, prefix="/api")
