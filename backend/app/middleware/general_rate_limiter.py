"""
app/middleware/general_rate_limiter.py
Owner: Developer 2 (Backend / Simulation)

Global rate limiting middleware for all incoming requests (including GET endpoints).
Reuses the shared in-memory _store, sliding window, and locking pattern from rate_limiter.py.
Exempts /health from rate limits.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.middleware.client_ip import get_trusted_client_ip
from app.middleware.rate_limiter import record_and_check_rate_limit


class GeneralRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Applies sliding-window rate limit (default 60 req/60s per IP) across all HTTP routes.
    /health is exempt so liveness checks are never blocked.
    """

    async def dispatch(self, request: Request, call_next):
        # Liveness checks & interactive demo endpoints are exempt from strict rate limiting
        if request.url.path.startswith(("/health", "/simulator", "/agent", "/reports", "/incidents")):
            return await call_next(request)

        ip = get_trusted_client_ip(request)
        max_calls = settings.GENERAL_RATE_LIMIT_MAX
        window_seconds = settings.GENERAL_RATE_LIMIT_WINDOW

        allowed, retry_after = record_and_check_rate_limit(
            ip=ip,
            bucket="general",
            max_calls=max_calls,
            window_seconds=window_seconds,
        )

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Max {max_calls} requests per {window_seconds}s. Please slow down."
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
