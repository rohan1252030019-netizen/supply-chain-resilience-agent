"""
app/middleware/security.py
Owner: Developer 2 (Backend / Simulation)

Security middleware components:
  1. SecurityHeadersMiddleware — injects defensive HTTP response headers on every response.
  2. SecurityEventLoggerMiddleware — logs all 4xx/5xx responses with IP + path for monitoring.
  3. RequestSizeLimitMiddleware — counts actual streamed bytes and enforces body size limit (64 KB).
  4. require_api_key — optional FastAPI Depends() enforcing X-API-Key with constant-time comparison.

IMPORTANT: None of this changes business logic, DB models, or existing route behavior.
"""

import logging
import secrets
from fastapi import Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from app.config import settings
from app.middleware.client_ip import get_trusted_client_ip

logger = logging.getLogger("security")


def _sanitize_log_str(val: str) -> str:
    """Strip carriage returns, newlines, and control characters to prevent log injection."""
    return "".join(ch for ch in val if ch.isprintable() and ch not in "\r\n")[:128]


# ---------------------------------------------------------------------------
# 1. HTTP Security Headers Middleware
# ---------------------------------------------------------------------------

SECURITY_HEADERS = {
    # Prevent browsers from MIME-sniffing a response away from the declared content-type.
    "X-Content-Type-Options": "nosniff",
    # Block the page from being displayed inside a frame (prevents clickjacking).
    "X-Frame-Options": "DENY",
    # Legacy XSS filter for older browsers.
    "X-XSS-Protection": "1; mode=block",
    # Control how much referrer information is sent.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Restrict access to browser features (camera, mic, geolocation).
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # Remove server fingerprint (replace default with opaque name).
    "Server": "scda",
    # Content Security Policy — restricts what sources the browser will load.
    "Content-Security-Policy": (
        "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'; "
        "connect-src *; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
    ),
    # HTTP Strict Transport Security — forces HTTPS in production.
    "Strict-Transport-Security": "max-age=31536000",
    # Prevent browser from sending data cross-origin.
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects comprehensive defensive security headers into every HTTP response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


# ---------------------------------------------------------------------------
# 2. Security Event Logger Middleware
# ---------------------------------------------------------------------------

class SecurityEventLoggerMiddleware(BaseHTTPMiddleware):
    """
    Logs every HTTP 4xx and 5xx response with IP, method, path, and status code.
    Provides a basic audit trail for detecting abuse, scanning, and auth failures.
    Uses get_trusted_client_ip to prevent spoofed X-Forwarded-For headers from polluting logs.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if response.status_code >= 400:
            ip = get_trusted_client_ip(request)
            level = logging.WARNING if response.status_code < 500 else logging.ERROR
            logger.log(
                level,
                "SECURITY_EVENT | status=%d | method=%s | path=%s | ip=%s",
                response.status_code,
                _sanitize_log_str(request.method),
                _sanitize_log_str(request.url.path),
                _sanitize_log_str(ip),
            )

        return response


# ---------------------------------------------------------------------------
# 3. Request Body Size Limiter (Stream-counting + Header check)
# ---------------------------------------------------------------------------

class RequestSizeLimitMiddleware:
    """
    Rejects requests with a body larger than max_bytes (default: 64 KB).
    Counts actual body bytes streamed in (handles chunked transfer encoding and understated headers)
    in addition to the fast-path Content-Length header check.
    """

    def __init__(self, app, max_bytes: int = 65_536):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast-path check: Content-Length header (cheap early rejection)
        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")
        if content_length_raw:
            try:
                if int(content_length_raw.decode("latin1")) > self.max_bytes:
                    logger.warning(
                        "SECURITY_EVENT | OVERSIZED_REQUEST | content-length=%s | max_bytes=%d",
                        _sanitize_log_str(content_length_raw.decode("latin1", errors="ignore")),
                        self.max_bytes,
                    )
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": f"Request body too large. Maximum allowed: {self.max_bytes} bytes."},
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        # Stream-level byte counter: catches chunked encoding and missing/understated Content-Length
        bytes_received = 0
        chunks = []
        oversized = False

        while True:
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                bytes_received += len(body)
                chunks.append(message)
                if bytes_received > self.max_bytes:
                    oversized = True
                    break
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                chunks.append(message)
                break

        if oversized:
            logger.warning(
                "SECURITY_EVENT | OVERSIZED_STREAM | bytes_received=%d | max_bytes=%d",
                bytes_received,
                self.max_bytes,
            )
            response = JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large. Maximum allowed: {self.max_bytes} bytes."},
            )
            await response(scope, receive, send)
            return

        # Replay the chunks to the downstream application
        chunk_iter = iter(chunks)

        async def replay_receive():
            try:
                return next(chunk_iter)
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)


# ---------------------------------------------------------------------------
# 4. Optional API Key Dependency (Timing Attack Protected)
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(_api_key_header)) -> None:
    """
    FastAPI dependency for optional API key enforcement on mutating endpoints.

    - If settings.API_KEY is empty (default): open access — safe for local dev/demo.
    - If settings.API_KEY is set in .env: all mutating endpoints require matching X-API-Key.
    - Uses constant-time comparison (secrets.compare_digest) to prevent side-channel timing attacks.
    """
    if not settings.API_KEY:
        return  # Open mode — API_KEY not configured

    if not api_key or not secrets.compare_digest(api_key, settings.API_KEY):
        logger.warning("SECURITY_EVENT | INVALID_API_KEY | provided=%s", bool(api_key))
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide a valid X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

_bearer_security = HTTPBearer(auto_error=False)


async def require_api_key_or_user(
    api_key: str = Security(_api_key_header),
    auth: HTTPAuthorizationCredentials = Security(_bearer_security),
) -> None:
    if not settings.API_KEY:
        return
    if api_key and secrets.compare_digest(api_key, settings.API_KEY):
        return
    if auth and auth.credentials:
        try:
            payload = jwt.decode(auth.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("sub"):
                return
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="Authentication required (API key or login token).")

