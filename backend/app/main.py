import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.db import check_db_connection
from app.core.observability import configure_sentry
from app.core.security_headers import SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO)

settings = get_settings()
is_production = settings.environment == "production"

# Before the app exists, so anything raised while wiring it up is reported too.
configure_sentry(settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    check_db_connection()
    yield


app = FastAPI(
    title=settings.project_name,
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added last so it wraps CORSMiddleware: preflight responses are answered by CORS
# itself and would otherwise go out without any security header. HSTS is keyed off
# the environment rather than the request scheme because Render terminates TLS and
# talks plain HTTP to the container, and because sending HSTS over http://localhost
# would poison the browser's HSTS cache for every other local project.
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.environment != "local")

app.include_router(health_router)
