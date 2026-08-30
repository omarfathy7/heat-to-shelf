import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.routes import health, products, shipments
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

configure_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(products.router, prefix=settings.api_prefix)
    app.include_router(shipments.router, prefix=settings.api_prefix)
    return app


app = create_app()