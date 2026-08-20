"""Security headers added to every HTTP response.

Registered last in main.py, which makes it the outermost middleware: Starlette
inserts each new middleware at the front of its list and builds the stack in
reverse. That ordering matters because CORSMiddleware answers preflight requests
itself without ever reaching the router, so only a middleware sitting outside it
can put headers on those responses.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# This service only ever returns JSON, so it needs permission to load nothing at all.
STRICT_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# Swagger UI and ReDoc are real HTML pages pulling assets from a CDN. 'unsafe-inline'
# for scripts is unavoidable: FastAPI's get_swagger_ui_html() emits an inline <script>
# that boots SwaggerUIBundle. ReDoc pulls Montserrat and Roboto from Google Fonts,
# injects its styles at runtime and spawns web workers from blob: URLs. The looser
# policy is confined to DOCS_PATHS, and those routes are already switched off in
# production (see docs_url=None in main.py).
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# /openapi.json is deliberately absent: it is JSON, so it keeps the strict policy.
DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})

# One year. No `preload` directive: the service is hosted under onrender.com, a
# domain we do not own and must not submit to the preload list.
HSTS_VALUE = "max-age=31536000; includeSubDomains"

BASE_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    # A URL that carries a capability token in its path must never travel to a
    # third party in a Referer header.
    "referrer-policy": "no-referrer",
    "permissions-policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
}


class SecurityHeadersMiddleware:
    """Pure ASGI middleware: it only rewrites the response start message.

    Deliberately not a BaseHTTPMiddleware subclass — that one buffers through an
    anyio task group, which breaks streaming responses and background tasks for
    no gain when all we do is set a handful of headers.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        hsts: bool,
        docs_paths: frozenset[str] = DOCS_PATHS,
    ) -> None:
        self.app = app
        self.hsts = hsts
        self.docs_paths = docs_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        csp = DOCS_CSP if scope["path"] in self.docs_paths else STRICT_CSP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                # MutableHeaders replaces an existing header instead of appending a
                # second copy of it, so these values always win and never duplicate.
                headers = MutableHeaders(scope=message)
                for name, value in BASE_HEADERS.items():
                    headers[name] = value
                headers["content-security-policy"] = csp
                if self.hsts:
                    headers["strict-transport-security"] = HSTS_VALUE
            await send(message)

        await self.app(scope, receive, send_with_headers)
