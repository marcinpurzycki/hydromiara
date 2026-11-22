"""Response headers and the request body limit, as plain ASGI middleware.

The API and the page are served under one host name (the proxy sends the
`/api` path to this service), so the browser needs no cross-origin access and
none is opened here. Transport security (TLS, HSTS) belongs to the proxy that
terminates TLS, not to this service.
"""

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api import limits

# Nothing in a JSON answer may load or run anything, and nothing may frame it.
_STRICT_CSP = "default-src 'none'; frame-ancestors 'none'"

# The interactive description of the interface is a page that loads its script
# and style from the public CDN FastAPI points it to and starts with an inline
# script, so it cannot carry the strict policy; it still may not be framed.
_DOCS_CSP = "frame-ancestors 'none'"

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    # The declared content type is final; browsers must not guess another.
    ("X-Content-Type-Options", "nosniff"),
    # The address of a Report is the only key to it: never sent on as a referrer.
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
)

# A Report is reachable by anyone who knows its address, so no cache on the
# way (proxy, browser) may keep a copy.
CACHE_CONTROL = "no-store"


class SecurityHeadersMiddleware:
    """Adds the security headers to every HTTP response, errors included."""

    def __init__(self, app: ASGIApp, *, docs_paths: tuple[str, ...] = ()) -> None:
        self.app = app
        self.docs_paths = docs_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        policy = _DOCS_CSP if scope["path"] in self.docs_paths else _STRICT_CSP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers[name] = value
                headers["Content-Security-Policy"] = policy
                if "cache-control" not in headers:
                    headers["Cache-Control"] = CACHE_CONTROL
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


class BodyLimitMiddleware:
    """Refuses a request whose body is, or could be, larger than the limit.

    The declared length is checked before anything is read. A body sent in
    chunks has no declared length, so it is refused: every client of this API
    sends a short JSON document with its length.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = limits.MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        refusal = None
        if "transfer-encoding" in headers:
            refusal = _error(
                411, "length_required", "Żądanie musi podawać długość treści (Content-Length)."
            )
        else:
            declared = headers.get("content-length", "0").strip()
            if not declared.isascii() or not declared.isdigit():
                refusal = _error(400, "invalid_request", "Nieprawidłowy nagłówek Content-Length.")
            elif int(declared) > self.max_bytes:
                refusal = _error(
                    413,
                    "request_too_large",
                    f"Treść żądania jest za duża (najwyżej {self.max_bytes} bajtów).",
                )
        if refusal is not None:
            await refusal(scope, receive, send)
            return
        await self.app(scope, receive, send)
