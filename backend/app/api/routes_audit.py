"""
app/api/routes_audit.py
Owner: Developer 2 (Backend / Simulation)

RECEIVES: rows written by app/audit/audit_logger.py (called from every tool + agent decision)
DELIVERS: chronological timeline to the frontend Audit page (docs Section 17)
"""

import sys
import os
import logging

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

logger = logging.getLogger(__name__)

from datetime import datetime, timezone
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.common import AuditLogOut
from app.middleware.rate_limiter import check_rate_limit
from app.middleware.security import require_api_key
from seed_data.broken_data import BROKEN_SCENARIOS, inject_broken_data
from app.core.deps import require_admin

router = APIRouter()


class BrokenDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str = Field(..., pattern="^(inventory|suppliers|purchase_orders|production_orders|audit_logs|integration_errors|all)$")

_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


def get_repo(db: Database = Depends(get_mongo_db)):
    return AuditLogRepository(db)


@router.get("/", response_model=list[AuditLogOut])
def list_audit_logs(
    incident_id: Optional[str] = Query(None, pattern=_ID_PATTERN, max_length=32),
    repo: AuditLogRepository = Depends(get_repo),
    current_user: dict = Depends(require_admin),
):
    """GET /audit?incident_id=INC-001 -> full or incident-scoped audit timeline."""
    if incident_id:
        return repo.get_by_incident_id(incident_id)
    return repo.list_all()


@router.get("/diagnostics")
def list_diagnostics(
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(require_admin),
):
    """Engineering-facing integration and data-quality records."""
    audit_logs = list(db["audit_logs"].find(
        {"$or": [
            {"incident_id": None},
            {"event_type": {"$in": ["WORKFLOW_FAILED", "DUPLICATE_EVENT"]}},
        ]},
        {"_id": 0},
    ).sort("timestamp", -1))
    integration_errors = list(db["integration_errors"].find({}, {"_id": 0}).sort("timestamp", -1))
    return {"audit_logs": audit_logs, "integration_errors": integration_errors}


@router.post("/diagnostics/inject")
def inject_diagnostics(
    payload: BrokenDataRequest,
    request: Request,
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(require_admin),
):
    """Explicitly inject test fixtures; never called during normal startup."""
    check_rate_limit(request, bucket="diagnostics_inject", max_calls=10, window_seconds=60)
    if payload.scenario not in BROKEN_SCENARIOS:
        raise HTTPException(status_code=422, detail="Unknown diagnostic scenario")
    inject_broken_data(db, payload.scenario)
    return {"scenario": payload.scenario, "message": "Diagnostic fixtures injected."}


def _report_text(value) -> str:
    return str(value or "").encode("latin-1", "replace").decode("latin-1")


def _report_date(value: Optional[str], field_name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}; use ISO date format.") from exc


from app.services.report_generator import (
    fetch_report_context,
    generate_report_narrative,
    build_operations_pdf,
    generate_report_bundle,
)


@router.get("/report/preview")
def operator_report_preview(
    request: Request,
    incident_id: Optional[str] = Query(None, pattern=_ID_PATTERN, max_length=32),
    start_date: Optional[str] = Query(None, max_length=40),
    end_date: Optional[str] = Query(None, max_length=40),
    include_diagnostics: bool = Query(False),
    order_id: Optional[str] = Query(None, max_length=64),
    supplier_id: Optional[str] = Query(None, max_length=64),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(require_admin),
):
    """
    Returns the LLM synthesized narrative and aggregated operational context as JSON
    for instant in-browser viewing and dashboard insights.
    """
    check_rate_limit(request, bucket="operator_pdf_report", max_calls=30, window_seconds=60)
    start = _report_date(start_date, "start_date")
    end = _report_date(end_date, "end_date")
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start_date must be before end_date.")

    if incident_id:
        incident = db["incidents"].find_one({"incident_id": incident_id}, {"_id": 0})
        if not incident:
            raise HTTPException(status_code=404, detail="incident not found")

    context = fetch_report_context(
        db=db,
        incident_id=incident_id,
        start_date=start,
        end_date=end,
        include_diagnostics=include_diagnostics,
        order_id=order_id,
        supplier_id=supplier_id,
    )
    narrative = generate_report_narrative(context)
    return {
        "summary_stats": context["summary_stats"],
        "narrative": narrative,
        "primary_incident": context.get("primary_incident"),
        "primary_plan": context.get("primary_plan"),
        "recommended_option": context.get("recommended_option"),
        "inventory_count": len(context.get("inventory", [])),
        "production_count": len(context.get("production_orders", [])),
        "po_count": len(context.get("purchase_orders", [])),
    }


@router.get("/report/operator.pdf")
def operator_report_pdf(
    request: Request,
    incident_id: Optional[str] = Query(None, pattern=_ID_PATTERN, max_length=32),
    start_date: Optional[str] = Query(None, max_length=40),
    end_date: Optional[str] = Query(None, max_length=40),
    include_diagnostics: bool = Query(False),
    order_id: Optional[str] = Query(None, max_length=64),
    supplier_id: Optional[str] = Query(None, max_length=64),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(require_admin),
):
    """Generate a comprehensive, LLM-synthesized operations report PDF."""
    check_rate_limit(request, bucket="operator_pdf_report", max_calls=20, window_seconds=60)

    start = _report_date(start_date, "start_date")
    end = _report_date(end_date, "end_date")
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start_date must be before end_date.")

    if incident_id:
        incident = db["incidents"].find_one({"incident_id": incident_id}, {"_id": 0})
        if not incident:
            raise HTTPException(status_code=404, detail="incident not found")

    bundle = generate_report_bundle(
        db=db,
        incident_id=incident_id,
        start_date=start,
        end_date=end,
        include_diagnostics=include_diagnostics,
        order_id=order_id,
        supplier_id=supplier_id,
    )

    suffix = order_id or supplier_id or incident_id or "operations"
    filename = f"supply-chain-report-{suffix}-{datetime.now(timezone.utc).date().isoformat()}.pdf"
    return Response(
        content=bundle["pdf_bytes"],
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

