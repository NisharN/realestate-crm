from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import auth, dashboard, leads, listings, settings, v1, workflow
from app.config import get_settings
from app.db import engine, init_db
from app.services.webhooks import deliver_soon

logger = logging.getLogger("crm")
SWEEP_INTERVAL_S = 30


async def _sweeper() -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_S)
        await deliver_soon()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    if cfg.is_production and cfg.jwt_secret == "change-me-in-production":
        raise RuntimeError("CRM_JWT_SECRET must be set in production")
    await init_db()
    if cfg.demo_seed:
        from app.seed import seed_demo

        await seed_demo()
    task = asyncio.create_task(_sweeper())
    try:
        yield
    finally:
        task.cancel()


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(title=cfg.app_name, version="0.1.0", lifespan=lifespan, docs_url="/docs")
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        async with engine().connect() as conn:
            await conn.execute(text("select 1"))
        return {"status": "ok", "service": "realestate-crm", "version": app.version}

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    for r in (auth.router, leads.router, listings.router, workflow.router, settings.router, dashboard.router):
        app.include_router(r, prefix="/api")
    app.include_router(v1.router)
    return app


app = create_app()
