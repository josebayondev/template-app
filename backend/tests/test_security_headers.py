import re

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.security_headers import (
    BASE_HEADERS,
    DOCS_CSP,
    HSTS_VALUE,
    STRICT_CSP,
    SecurityHeadersMiddleware,
)
from app.main import app as real_app
from tests.conftest import TEST_CORS_ORIGIN


async def _ok(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def _already_framed(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})


def build_client(*, hsts: bool = False) -> TestClient:
    """A throwaway app wrapped in the middleware, so these tests do not depend on
    how main.py happens to be wired, nor open a database connection."""
    routes = [
        Route(path, _ok)
        for path in ("/thing", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json")
    ]
    routes.append(Route("/already-framed", _already_framed))
    return TestClient(SecurityHeadersMiddleware(Starlette(routes=routes), hsts=hsts))


def test_base_headers_are_present() -> None:
    response = build_client().get("/thing")

    assert response.status_code == 200
    for name, value in BASE_HEADERS.items():
        assert response.headers[name] == value


def test_api_route_gets_the_strict_csp() -> None:
    response = build_client().get("/thing")

    assert response.headers["content-security-policy"] == STRICT_CSP


@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect", "/redoc"])
def test_docs_routes_get_the_relaxed_csp(path: str) -> None:
    response = build_client().get(path)

    assert response.headers["content-security-policy"] == DOCS_CSP
    # The relaxed policy only loosens what Swagger and ReDoc need; the rest holds.
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize(
    "html",
    [
        get_swagger_ui_html(openapi_url="/openapi.json", title="docs").body.decode(),
        get_redoc_html(openapi_url="/openapi.json", title="docs").body.decode(),
    ],
    ids=["swagger", "redoc"],
)
def test_docs_csp_allows_every_origin_the_docs_pages_load(html: str) -> None:
    """Guards against FastAPI changing where it pulls its assets from: a new CDN
    would silently render a blank docs page instead of failing loudly."""
    origins = set(re.findall(r'(?:src|href)="(https://[^/"]+)', html))

    assert origins, "the docs page stopped loading anything external, revisit DOCS_CSP"
    assert sorted(origin for origin in origins if origin not in DOCS_CSP) == []


def test_openapi_schema_keeps_the_strict_csp() -> None:
    response = build_client().get("/openapi.json")

    assert response.headers["content-security-policy"] == STRICT_CSP


def test_hsts_is_absent_when_disabled() -> None:
    response = build_client(hsts=False).get("/thing")

    assert "strict-transport-security" not in response.headers


def test_hsts_is_sent_when_enabled() -> None:
    response = build_client(hsts=True).get("/thing")

    assert response.headers["strict-transport-security"] == HSTS_VALUE
    assert "preload" not in response.headers["strict-transport-security"]


def test_headers_reach_responses_the_router_did_not_produce() -> None:
    response = build_client().get("/no-such-route")

    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == STRICT_CSP


def test_a_header_set_by_the_endpoint_is_replaced_not_duplicated() -> None:
    response = build_client().get("/already-framed")

    assert response.headers.get_list("x-frame-options") == ["DENY"]


def test_real_app_sends_the_headers() -> None:
    # No `with`: the lifespan (and its database check) is not needed here.
    response = TestClient(real_app).get("/health")

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == STRICT_CSP
    for name, value in BASE_HEADERS.items():
        assert response.headers[name] == value


def test_cors_preflight_also_carries_the_headers() -> None:
    """CORSMiddleware answers preflights itself, without ever reaching the router, so
    these headers appear only if the security middleware sits outside it."""
    response = TestClient(real_app).options(
        "/health",
        headers={
            "Origin": TEST_CORS_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == TEST_CORS_ORIGIN
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == STRICT_CSP


def test_allowed_preflight_keeps_both_cors_and_security_headers() -> None:
    """The accepted-origin half of the same property, wired like main.py does it:
    CORS added first, security added last so it ends up outermost. Built here with
    an explicit origin so the result does not depend on the ambient CORS_ORIGINS.
    """
    origin = "https://front.example"
    inner = Starlette(routes=[Route("/thing", _ok)])
    inner.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    inner.add_middleware(SecurityHeadersMiddleware, hsts=False)

    response = TestClient(inner).options(
        "/thing",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == STRICT_CSP
