"""
app/routers/config.py

Config router: provides runtime configuration to n8n.

ENDPOINT:
    GET /api/v1/config/n8n  →  N8NConfigResponse (JSON)

PURPOSE:
    n8n fetches this endpoint once at the start of each incident lifecycle.
    The response dynamically supplies email addresses, the autonomous approval
    threshold, the backend URL, and LLM parameters — removing all hard-coded
    $env references from workflow nodes and centralizing config in one place.

SECURITY:
    Protected by `require_api_key` (X-API-Key header, constant-time verified).

ERROR HANDLING:
    - Missing required env vars → HTTP 500 with a diagnostic detail field
      listing which variables are unset, so ops can debug quickly.
    - Invalid email format detected by Pydantic → HTTP 422 (handled by
      FastAPI's global validation handler in main.py).
"""

import sys
import os
import logging

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.core.security import require_api_key
from app.schemas.config import LLMConfig, N8NConfigResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_required_vars() -> list[str]:
    """
    Returns a list of variable names that are required but unset/empty.
    Called before constructing N8NConfigResponse to produce useful 500 errors.
    """
    required: dict[str, Optional[str]] = {
        "NOTIFY_FROM_EMAIL": settings.NOTIFY_FROM_EMAIL,
        "APPROVAL_NOTIFY_EMAIL": settings.APPROVAL_NOTIFY_EMAIL,
        "OPS_ALERT_EMAIL": settings.OPS_ALERT_EMAIL,
        "BACKEND_URL": settings.BACKEND_URL,
        "GROQ_MODEL": settings.GROQ_MODEL,
        "LLM_PROVIDER": settings.LLM_PROVIDER,
    }
    return [name for name, value in required.items() if not value]


@router.get(
    "/n8n",
    response_model=N8NConfigResponse,
    summary="n8n Runtime Configuration",
    description=(
        "Returns runtime configuration consumed by n8n at the start of each "
        "incident lifecycle. Dynamically supplies email addresses, approval "
        "thresholds, and LLM parameters so workflow nodes need no hard-coded "
        "environment variable references."
    ),
    tags=["Config"],
)
def get_n8n_config(
    _auth: None = Depends(require_api_key),
) -> N8NConfigResponse:
    """
    Protected config endpoint — called by n8n's 'Fetch Backend Config' node.

    Returns:
        N8NConfigResponse: fully validated config payload.

    Raises:
        HTTP 401: X-API-Key missing or invalid.
        HTTP 500: One or more required environment variables are not set.
    """
    # Pre-flight: check for unset required vars before Pydantic validation
    # so the error message is actionable (lists the missing var names).
    missing = _check_required_vars()
    if missing:
        logger.error(
            "Config endpoint called but required env vars are unset: %s",
            missing,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Server configuration incomplete",
                "missing_variables": missing,
                "hint": (
                    "Set the listed variables in your .env file and restart "
                    "the backend service."
                ),
            },
        )

    try:
        return N8NConfigResponse(
            notify_from_email=settings.NOTIFY_FROM_EMAIL,
            approval_notify_email=settings.APPROVAL_NOTIFY_EMAIL,
            ops_alert_email=settings.OPS_ALERT_EMAIL,
            autonomous_approval_limit_usd=settings.AUTONOMOUS_APPROVAL_LIMIT_USD,
            backend_url=settings.BACKEND_URL,
            llm_config=LLMConfig(
                provider=settings.LLM_PROVIDER,
                model=settings.GROQ_MODEL,
                temperature=settings.GROQ_TEMPERATURE,
            ),
        )
    except Exception as exc:
        logger.exception("Failed to build N8NConfigResponse: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to build config response",
                "hint": str(exc),
            },
        ) from exc
