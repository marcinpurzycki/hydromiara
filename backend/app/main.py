"""Hydromiara API: application object and route registration."""

from fastapi import APIRouter, FastAPI

from app.api import analyses, catalog, parcels, reports, simulation
from app.api.errors import register_error_handlers
from app.orchestrator.runtime import lifespan

API_PREFIX = "/api"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hydromiara API",
        version="0.1.0",
        description="Ocena sytuacji wodnej działki i rekomendacje. Wszystkie trasy pod /api.",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    register_error_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(catalog.router)
    api.include_router(parcels.router)
    api.include_router(analyses.router)
    api.include_router(reports.router)
    api.include_router(simulation.router)
    app.include_router(api)
    return app


app = create_app()
