"""
app/main.py
Owner: Developer 2 (Backend / Simulation)

FastAPI application entrypoint. Mounts every router from app/api/*, enables CORS
for the React frontend, and initializes MongoDB + seed data on startup.

NOTE: LLM logic is handled entirely in the n8n workflow (Groq AI Agent node).
This backend is a pure CRUD / data API — no LLM provider configured here.

DELIVERS:
  - Swagger UI at /docs — fastest API contract sanity-check for the full team
  - /integrations/* — n8n-only endpoints (ERP event, delivery breach, supplier response, audit)
  - /agent/* — agent state machine (trigger, approve, reject, state, plan)
  - /incidents, /inventory, /suppliers, /production, /audit, /simulator — frontend + agent

SECURITY LAYERS (all non-breaking):
  Layer 1 — RequestSizeLimitMiddleware : reject bodies > 64 KB (header + streaming check)
  Layer 2 — GeneralRateLimitMiddleware : global sliding-window rate limit (60/60s, /health exempt)
  Layer 3 — SecurityHeadersMiddleware  : X-Frame-Options, CSP, HSTS, etc. on all responses
  Layer 4 — SecurityEventLoggerMiddleware : log all 4xx/5xx events with IP for monitoring
  Layer 5 — CORSMiddleware             : restricted origins, methods, and headers
  Layer 6 — Global 500 handler         : never leak raw tracebacks to API clients
  Layer 7 — Custom 422 handler         : sanitize validation error output
  Layer 8 — Path param regex           : per-route, blocks injection/traversal (see routes_*)
  Layer 9 — API Key dependency         : opt-in via settings.API_KEY on mutating endpoints
"""

from contextlib import asynccontextmanager
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.mongo_database import get_mongo_db, ping_mongo
from seed_data.seed_data import run as seed_run

from app.middleware.security import (
    SecurityHeadersMiddleware,
    SecurityEventLoggerMiddleware,
    RequestSizeLimitMiddleware,
)
from app.middleware.general_rate_limiter import GeneralRateLimitMiddleware

from app.api import (
    routes_inventory,
    routes_suppliers,
    routes_production,
    routes_incidents,
    routes_audit,
    routes_agent,
    routes_simulator,
    routes_integrations,
    routes_auth,
)
from app.routers import config as config_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ping_mongo()
        db = get_mongo_db()
        seed_run(db)
        db["audit_logs"].update_many(
            {"timestamp": {"$exists": False}},
            {"$set": {"timestamp": datetime.now(timezone.utc)}},
        )
    except Exception as err:
        logger.warning(f"[Startup Warning] Database initialization skipped or non-fatal: {err}")
    yield


app = FastAPI(
    title="Supply Chain Disruption Control Agent",
    description="Autonomous incident triage & multi-modal re-routing engine (HOP 2026)",
    version="0.1.0",
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    lifespan=lifespan,
)

# ── Layer 1: Request body size limit (64 KB, stream counting + header check) ─
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=65_536)

# ── Layer 2: Global general rate limiter (60 req/60s across all routes, /health exempt) ──
app.add_middleware(GeneralRateLimitMiddleware)

# ── Layer 3: Security headers on every response ──────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)

# ── Layer 4: Security event logger (4xx / 5xx monitoring) ────────────────────
app.add_middleware(SecurityEventLoggerMiddleware)

# ── Layer 5: CORS — restricted to known origins and explicit HTTP methods ─────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Set-Cookie"],
)


# ── Layer 6: Global 500 handler — never leak tracebacks ──────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# ── Layer 7: Custom 422 handler — sanitize validation errors ──────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Return safe, simplified validation errors.
    Strips internal field paths and Python type names that could fingerprint the backend.
    """
    safe_errors = []
    for error in exc.errors():
        safe_errors.append({
            "field": " -> ".join(str(loc) for loc in error.get("loc", [])),
            "issue": error.get("msg", "Invalid value"),
        })
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed.", "errors": safe_errors},
    )


@app.get("/")
def root():
    """Root endpoint providing service overview and documentation links."""
    return {
        "status": "active",
        "service": "Supply Chain Disruption Control Agent API Engine",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health():
    """Simple liveness check. Does not expose version or internal state."""
    return {"status": "ok", "service": "supply-chain-disruption-control-agent"}


# --- Mount all routers. Prefixes MUST match docs/API_CONTRACTS.md exactly. ---
# --- Authentication (public endpoints — no auth dependency) ---
app.include_router(routes_auth.router, prefix="/auth", tags=["Auth"])
# --- Core data routes ---
app.include_router(routes_inventory.router, prefix="/inventory", tags=["Inventory"])
app.include_router(routes_suppliers.router, prefix="/suppliers", tags=["Suppliers"])
app.include_router(routes_production.router, prefix="/production", tags=["Production"])
app.include_router(routes_incidents.router, prefix="/incidents", tags=["Incidents"])
app.include_router(routes_audit.router, prefix="/audit", tags=["Audit"])
app.include_router(routes_agent.router, prefix="/agent", tags=["Agent"])
app.include_router(routes_simulator.router, prefix="/simulator", tags=["Simulator"])
# --- n8n integration layer (called by n8n workflow, not frontend) ---
app.include_router(routes_integrations.router, prefix="/integrations", tags=["N8N Integrations"])
# --- Config endpoint: serves runtime config to n8n at incident lifecycle start ---
app.include_router(config_router.router, prefix="/api/v1/config", tags=["Config"])
