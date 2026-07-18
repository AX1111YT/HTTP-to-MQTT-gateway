from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from gateway.api.v1.router import api_router
from gateway.config import settings
from gateway.logging_setup import setup_logging
from gateway.mqtt.client import mqtt_client
from gateway.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(settings.LOG_LEVEL)
    logger.info("gateway starting", extra={"env": settings.ENV})

    await mqtt_client.start()

    yield

    await mqtt_client.stop()
    logger.info("gateway stopped")


def create_app() -> FastAPI:
    app_kwargs: dict[str, Any] = {"lifespan": lifespan}
    if settings.ENV == "production":
        app_kwargs.update({"docs_url": None, "redoc_url": None, "openapi_url": None})

    app = FastAPI(**app_kwargs)
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Any:
        req_id = str(uuid.uuid4())
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    app.include_router(api_router, prefix="/api/v1")

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "BearerAuth"
        ] = {"type": "http", "scheme": "bearer"}
        schema["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "unhandled exception", extra={"request_id": req_id, "error": repr(exc)}
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": req_id},
        )

    return app


app = create_app()
