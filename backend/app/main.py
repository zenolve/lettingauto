"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.logger import get_logger
from app.routers import (
    auth,
    checklist,
    contracts,
    dashboard,
    forms,
    landlords,
    library,
    offers,
    payments,
    properties,
    referencing,
    signatures,
    uploads,
    webhooks,
)
from app.routers.uploads import UPLOADS_ROOT

logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.brand_name} — Backend",
        version="1.0.0",
        description="FastAPI service replacing the n8n workflow for Palace Gate Lettings.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_base_url, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(properties.router)
    app.include_router(forms.router)
    app.include_router(contracts.router)
    app.include_router(library.router)
    app.include_router(referencing.router)
    app.include_router(checklist.router)
    app.include_router(landlords.router)
    app.include_router(offers.router)
    app.include_router(payments.router)
    app.include_router(signatures.router)
    app.include_router(uploads.router)
    app.include_router(webhooks.router)

    # Static mount so files saved via POST /api/uploads/{property_id}/{bucket}
    # are reachable at GET /uploads/{property_id}/{bucket}/<file>.
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_ROOT)), name="uploads")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
