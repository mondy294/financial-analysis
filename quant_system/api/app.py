from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from quant_system.api.errors import ApiError, api_error_handler, http_error_handler
from quant_system.api.routers import (
    clusters,
    definitions,
    health,
    jobs,
    meta,
    patterns,
    reports,
    signals,
    stocks,
    system,
)


def create_app(*, mount_frontend: bool | None = None) -> FastAPI:
    if mount_frontend is None:
        # qs serve --dev 会设 QS_SERVE_MOUNT_FRONTEND=0，避免旧 dist 盖住 Vite
        mount_frontend = os.environ.get("QS_SERVE_MOUNT_FRONTEND", "1") != "0"
    app = FastAPI(
        title="quant_system Web Console",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.on_event("startup")
    def _ensure_pattern_defs() -> None:
        """补表 + seed Pattern Definition（幂等）。"""
        try:
            from quant_system.database.migrations import ensure_schema_columns
            from quant_system.infra.db import session_scope
            from quant_system.patterns.store import ensure_seeded

            ensure_schema_columns()
            with session_scope() as session:
                ensure_seeded(session)
        except Exception:
            # 启动时 DB 不可用不阻断；扫描时 registry 会回退 seed
            pass
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)

    for router in (
        health.router,
        meta.router,
        stocks.router,
        clusters.router,
        # definitions 必须在 patterns 之前，避免 /patterns/{id} 吃掉 /definitions
        definitions.router,
        patterns.router,
        signals.router,
        reports.router,
        jobs.router,
        system.router,
    ):
        app.include_router(router, prefix="/api")

    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if mount_frontend and web_dist.exists():
        assets = web_dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(web_dist / "index.html")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api"):
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = web_dist / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(web_dist / "index.html")

    return app
