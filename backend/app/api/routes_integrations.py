"""
app/api/routes_integrations.py
Owner: Developer 2 (Backend / Simulation)

N8N Integration Layer — these endpoints are ONLY called by the n8n workflow, not the frontend.
They act as the data bridge between n8n event triggers and the MongoDB Atlas database.

RECEIVES calls from n8n nodes (authenticated via X-API-Key header):
  POST /integrations/erp/event          - ERP system pushes a purchase order event
  GET  /integrations/purchase-orders/active  - Delivery Monitor fetches active POs
  POST /integrations/delivery-breach    - n8n detected a delivery commitment breach
  POST /integrations/supplier-response  - Supplier sent an RFQ response
  POST /integrations/audit              - n8n persists a canonical audit event

DELIVERS:
  - Upserted documents in MongoDB collections
  - incident_id when a new incident is created (used by n8n to trigger the AI agent)

SECURITY HARDENING:
  - Constant-time API key verification (secrets.compare_digest)
  - Rate limiting on all mutating and PDF/CSV report generation endpoints
  - Strict regex parameter validation preventing Header Injection & NoSQL injection
  - Strict Pydantic payload sanitization
"""

import sys
import os

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import csv
import io
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Any
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.config import settings
from app.middleware.rate_limiter import check_rate_limit
from app.core.deps import get_current_user_optional

router = APIRouter()

_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


# ---------------------------------------------------------------------------
# Auth helper (Constant-time verified)
# ---------------------------------------------------------------------------

def verify_api_key(x_api_key: str = Header(default="")):
    """Constant-time verified shared-secret auth for n8n -> backend calls."""
    expected_key = settings.BACKEND_API_KEY or settings.API_KEY
    if expected_key:
        if not x_api_key or not secrets.compare_digest(x_api_key, expected_key):
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ERPEventPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: Optional[str] = Field(None, max_length=64)
    event_type: str = Field(..., max_length=64)
    timestamp: Optional[str] = Field(None, max_length=64)
    po_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    supplier_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    component_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    expected_delivery: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, max_length=32)
    source: Optional[str] = Field("erp", max_length=32)


class DeliveryBreachPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: str = Field("DELIVERY_COMMITMENT_BREACH", max_length=64)
    po_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    supplier_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    component_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    promised_date: Optional[str] = Field(None, max_length=64)
    current_expected_date: Optional[str] = Field(None, max_length=64)
    delay_days: int = 0


class SupplierResponsePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rfq_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    supplier_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    component_id: str = Field(..., max_length=32, pattern=_ID_PATTERN)
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    delivery_days: Optional[int] = None
    total_cost: Optional[float] = None
    expedite_available: bool = False
    expedite_fee: Optional[float] = None
    accepted: Optional[bool] = None
    timestamp: Optional[str] = Field(None, max_length=64)


class AuditEventPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: Optional[str] = Field(None, max_length=64)
    timestamp: Optional[str] = Field(None, max_length=64)
    source: str = Field("n8n", max_length=64)
    workflow: str = Field(..., max_length=128)
    event_type: str = Field(..., max_length=64)
    incident_id: Optional[str] = Field(None, max_length=64)
    entity_type: Optional[str] = Field(None, max_length=64)
    entity_id: Optional[str] = Field(None, max_length=64)
    action: Optional[str] = Field(None, max_length=128)
    status: str = Field("SUCCESS", max_length=32)
    input: Optional[dict] = Field(default_factory=dict)
    output: Optional[dict] = Field(default_factory=dict)
    correlation_id: Optional[str] = Field(None, max_length=64)
    retry_count: int = 0
    error_details: Optional[str] = Field(None, max_length=1024)
    notification_status: Optional[str] = Field(None, max_length=64)
    erp_log_ref: Optional[str] = Field(None, max_length=64)


class ERPLogPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    log_id: Optional[str] = Field(None, max_length=64)
    timestamp: Optional[str] = Field(None, max_length=64)
    action: str = Field(..., max_length=64)
    entity_type: str = Field(..., max_length=64)
    entity_id: str = Field(..., max_length=64)
    incident_id: Optional[str] = Field(None, max_length=64)
    performed_by: str = Field("n8n", max_length=64)
    details: Optional[dict] = Field(default_factory=dict)
    status: str = Field("SUCCESS", max_length=32)
    correlation_id: Optional[str] = Field(None, max_length=64)
    error_details: Optional[str] = Field(None, max_length=1024)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/erp/event")
def erp_event(
    payload: ERPEventPayload,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth=Depends(verify_api_key),
):
    """
    n8n ERP Event Sync workflow calls this after validating a purchase order event.
    Upserts the PO in MongoDB. If status is DELAYED, creates an incident and returns
    the incident_id so n8n can trigger the AI agent.
    """
    check_rate_limit(request, bucket="n8n_erp_event", max_calls=120, window_seconds=60)
    now = datetime.now(timezone.utc)

    # Upsert purchase order
    po_doc = {
        "po_id": payload.po_id,
        "supplier_id": payload.supplier_id,
        "component_id": payload.component_id,
        "quantity": payload.quantity,
        "unit_price": payload.unit_price,
        "expected_delivery": payload.expected_delivery,
        "status": payload.status,
        "last_event_type": payload.event_type,
        "last_erp_sync": now.isoformat(),
    }
    db["purchase_orders"].update_one(
        {"po_id": payload.po_id},
        {"$set": po_doc},
        upsert=True,
    )

    incident_id = None

    # Auto-create incident for DELAYED status
    if payload.status == "DELAYED":
        existing = db["incidents"].find_one(
            {"affected_po": payload.po_id, "status": {"$nin": ["RESOLVED", "CANCELLED"]}},
            {"incident_id": 1}
        )
        if existing:
            incident_id = existing["incident_id"]
        else:
            incident_id = f"INC-ERP-{payload.po_id}-{int(now.timestamp())}"
            db["incidents"].insert_one({
                "incident_id": incident_id,
                "type": "SUPPLIER_DELAY",
                "severity": "MEDIUM",
                "affected_component": payload.component_id,
                "affected_po": payload.po_id,
                "supplier_id": payload.supplier_id,
                "status": "DETECTED",
                "created_at": now,
                "source": "erp_event",
            })

    return {
        "success": True,
        "po_id": payload.po_id,
        "incident_id": incident_id,
        "agent_trigger_required": payload.status == "DELAYED",
    }


@router.get("/purchase-orders/active")
def get_active_purchase_orders(
    db: Database = Depends(get_mongo_db),
    x_api_key: str = Header(default=""),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    Returns all active (non-terminal) purchase orders.
    Accessible by n8n (via X-API-Key) or authenticated users (via Bearer token).
    If caller is a supplier, filters to only their purchase orders.
    """
    expected_key = settings.BACKEND_API_KEY or settings.API_KEY
    is_api_key_valid = bool(expected_key and x_api_key and secrets.compare_digest(x_api_key, expected_key))
    
    if not is_api_key_valid and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required (X-API-Key or Bearer token)")

    active_statuses = ["PENDING", "IN_TRANSIT", "DELAYED", "AT_RISK", "ORDERED", "OPEN"]
    query = {"status": {"$in": active_statuses}}
    
    if current_user and current_user.get("role") == "supplier":
        supplier_id = current_user.get("supplier_id")
        if supplier_id:
            query["supplier_id"] = supplier_id
        else:
            return []

    pos = list(
        db["purchase_orders"].find(
            query,
            {"_id": 0}
        ).limit(200)
    )
    return pos


@router.post("/delivery-breach")
def delivery_breach(
    payload: DeliveryBreachPayload,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth=Depends(verify_api_key),
):
    """
    n8n Delivery Commitment Monitor calls this when it detects a delivery breach.
    Creates a DELIVERY_COMMITMENT_BREACH incident and returns the incident_id.
    """
    check_rate_limit(request, bucket="n8n_breach", max_calls=60, window_seconds=60)
    now = datetime.now(timezone.utc)

    # Check for existing open incident for this PO
    existing = db["incidents"].find_one(
        {"affected_po": payload.po_id, "type": "DELIVERY_BREACH", "status": {"$nin": ["RESOLVED", "CANCELLED"]}},
        {"incident_id": 1}
    )
    if existing:
        return {
            "success": True,
            "incident_id": existing["incident_id"],
            "created": False,
            "message": "Existing open incident found — not creating a duplicate",
        }

    incident_id = f"INC-BREACH-{payload.po_id}-{int(now.timestamp())}"
    db["incidents"].insert_one({
        "incident_id": incident_id,
        "type": "DELIVERY_BREACH",
        "severity": "HIGH" if payload.delay_days > 7 else "MEDIUM",
        "affected_component": payload.component_id,
        "affected_po": payload.po_id,
        "supplier_id": payload.supplier_id,
        "status": "DETECTED",
        "created_at": now,
        "source": "delivery_monitor",
        "delay_days": payload.delay_days,
        "promised_date": payload.promised_date,
        "current_expected_date": payload.current_expected_date,
    })

    return {
        "success": True,
        "incident_id": incident_id,
        "created": True,
        "po_id": payload.po_id,
        "delay_days": payload.delay_days,
    }


@router.post("/supplier-response")
def supplier_response(
    payload: SupplierResponsePayload,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth=Depends(verify_api_key),
):
    """
    n8n Supplier Response Sync calls this when a supplier responds to an RFQ.
    Upserts the RFQ response and returns any ranked options from existing recovery plans.
    """
    check_rate_limit(request, bucket="n8n_supplier_resp", max_calls=60, window_seconds=60)
    now = datetime.now(timezone.utc)

    rfq_doc = {
        "rfq_id": payload.rfq_id,
        "supplier_id": payload.supplier_id,
        "component_id": payload.component_id,
        "quantity": payload.quantity,
        "unit_price": payload.unit_price,
        "delivery_days": payload.delivery_days,
        "total_cost": payload.total_cost,
        "expedite_available": payload.expedite_available,
        "expedite_fee": payload.expedite_fee,
        "accepted": payload.accepted,
        "received_at": now.isoformat(),
    }
    db["rfq_responses"].update_one(
        {"rfq_id": payload.rfq_id, "supplier_id": payload.supplier_id},
        {"$set": rfq_doc},
        upsert=True,
    )

    # Return ranked options if a recovery plan references this RFQ
    plan = db["recovery_plans"].find_one(
        {"component_id": payload.component_id},
        {"_id": 0, "options": 1}
    )
    options = plan.get("options", []) if plan else []

    return {
        "success": True,
        "rfq_id": payload.rfq_id,
        "supplier_id": payload.supplier_id,
        "options": options,
    }


@router.post("/audit")
def ingest_audit_event(
    payload: AuditEventPayload,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth=Depends(verify_api_key),
):
    """
    n8n Internal Audit Webhook — persists a canonical audit event to MongoDB Atlas.
    Called by every workflow section as the final step. No HTTP self-loop.
    """
    check_rate_limit(request, bucket="n8n_audit", max_calls=120, window_seconds=60)
    now = datetime.now(timezone.utc)
    event_id = payload.event_id or f"AUD-{int(now.timestamp() * 1000)}"
    entry = {
        "event_id": event_id,
        "timestamp": payload.timestamp or now.isoformat(),
        "source": payload.source,
        "workflow": payload.workflow,
        "event_type": payload.event_type,
        "incident_id": payload.incident_id,
        "entity_type": payload.entity_type,
        "entity_id": payload.entity_id,
        "action": payload.action,
        "status": payload.status,
        "input": payload.input or {},
        "output": payload.output or {},
        "ingested_at": now,
        # Flatten for frontend AuditLogOut schema compatibility
        "tool": payload.action,
        "result": payload.status,
        "decision": payload.event_type,
        "reason": f"n8n workflow: {payload.workflow}",
        # Extended observability fields
        "correlation_id": payload.correlation_id,
        "retry_count": payload.retry_count,
        "error_details": payload.error_details,
        "notification_status": payload.notification_status,
        "erp_log_ref": payload.erp_log_ref,
    }
    db["audit_logs"].insert_one(entry)

    return {
        "success": True,
        "event_id": event_id,
        "collection": "audit_logs",
    }


# ---------------------------------------------------------------------------
# ERP Log endpoints
# ---------------------------------------------------------------------------

@router.post("/erp/log")
def erp_log(
    payload: ERPLogPayload,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth=Depends(verify_api_key),
):
    """
    n8n logs every ERP update action here for full traceability.
    Called after: PO creation, inventory updates, incident status changes.
    """
    check_rate_limit(request, bucket="n8n_erp_log", max_calls=120, window_seconds=60)
    now = datetime.now(timezone.utc)
    log_id = payload.log_id or f"ERP-LOG-{int(now.timestamp() * 1000)}"
    entry = {
        "log_id": log_id,
        "timestamp": payload.timestamp or now.isoformat(),
        "action": payload.action,
        "entity_type": payload.entity_type,
        "entity_id": payload.entity_id,
        "incident_id": payload.incident_id,
        "performed_by": payload.performed_by,
        "details": payload.details or {},
        "status": payload.status,
        "correlation_id": payload.correlation_id,
        "error_details": payload.error_details,
        "ingested_at": now,
    }
    db["erp_logs"].insert_one(entry)
    return {"success": True, "log_id": log_id}


@router.get("/erp/logs")
def get_erp_logs(
    incident_id: Optional[str] = Query(None, pattern=_ID_PATTERN, max_length=32),
    entity_id: Optional[str] = Query(None, pattern=_ID_PATTERN, max_length=32),
    limit: int = Query(100, ge=1, le=500),
    db: Database = Depends(get_mongo_db),
    _auth=Depends(verify_api_key),
):
    """Returns ERP action logs, optionally filtered by incident or entity."""
    query: dict = {}
    if incident_id:
        query["incident_id"] = incident_id
    if entity_id:
        query["entity_id"] = entity_id
    logs = list(db["erp_logs"].find(query, {"_id": 0}).sort("timestamp", -1).limit(limit))
    return logs


# ---------------------------------------------------------------------------
# Audit Report endpoints — CSV and PDF
# ---------------------------------------------------------------------------

_AUDIT_CSV_COLUMNS = [
    "event_id", "correlation_id", "timestamp", "source", "workflow",
    "event_type", "incident_id", "entity_type", "entity_id", "action",
    "status", "decision", "reason", "retry_count", "error_details",
    "notification_status", "erp_log_ref",
]


@router.get("/audit/report/csv")
def audit_report_csv(
    request: Request,
    incident_id: Optional[str] = Query(None, pattern=_ID_PATTERN, max_length=32),
    db: Database = Depends(get_mongo_db),
):
    """
    Generates and streams a CSV audit trail report.
    Optionally filter by incident_id. Rate limited to 20/min.
    """
    check_rate_limit(request, bucket="audit_csv_report", max_calls=20, window_seconds=60)
    query: dict = {}
    if incident_id:
        query["incident_id"] = incident_id
    logs = list(db["audit_logs"].find(query, {"_id": 0}).sort("timestamp", 1))

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=_AUDIT_CSV_COLUMNS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for log in logs:
        writer.writerow({col: log.get(col, "") for col in _AUDIT_CSV_COLUMNS})

    output.seek(0)
    # Safe alphanumeric filename (blocks HTTP Response Header injection)
    safe_suffix = f"_{incident_id}" if incident_id else ""
    filename = f"audit_trail{safe_suffix}.csv"
    return Response(
        content=output.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit/report/pdf")
def audit_report_pdf(
    request: Request,
    incident_id: Optional[str] = Query(None, pattern=_ID_PATTERN, max_length=32),
    db: Database = Depends(get_mongo_db),
):
    """
    Generates and streams a PDF audit trail report using fpdf2.
    Optionally filter by incident_id. Rate limited to 15/min (CPU protection).
    """
    check_rate_limit(request, bucket="audit_pdf_report", max_calls=15, window_seconds=60)
    try:
        from fpdf import FPDF
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="fpdf2 is not installed. Run: pip install fpdf2"
        )

    query: dict = {}
    if incident_id:
        query["incident_id"] = incident_id
    logs = list(db["audit_logs"].find(query, {"_id": 0}).sort("timestamp", 1))

    # --------------- Build PDF ---------------
    def _to_latin1(text: Any) -> str:
        return str(text or "").encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 14)
    title = f"Supply Chain Resilience Agent - Audit Trail Report"
    if incident_id:
        title += f" [{incident_id}]"
    pdf.cell(0, 10, _to_latin1(title), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 6, f"Generated: {datetime.now(timezone.utc).isoformat()} UTC  |  Total events: {len(logs)}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    # Table header
    col_widths = [36, 30, 44, 28, 30, 24, 22, 18, 16, 12, 0]
    col_labels = ["Event ID", "Correlation ID", "Timestamp", "Workflow", "Event Type",
                  "Incident", "Entity", "Action", "Status", "Retries", "Reason"]
    # Compute last column width
    total_fixed = sum(col_widths[:-1])
    page_w = pdf.w - 2 * pdf.l_margin
    col_widths[-1] = max(10, page_w - total_fixed)

    pdf.set_font("Helvetica", "B", 7)
    pdf.set_fill_color(30, 58, 138)
    pdf.set_text_color(255, 255, 255)
    for i, label in enumerate(col_labels):
        pdf.cell(col_widths[i], 7, label, border=1, fill=True, align="C")
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 6)
    pdf.set_text_color(0, 0, 0)
    fill = False
    for log in logs:
        row = [
            _to_latin1(log.get("event_id", ""))[:32],
            _to_latin1(log.get("correlation_id") or "")[:26],
            _to_latin1(log.get("timestamp", ""))[:40],
            _to_latin1(log.get("workflow", ""))[:26],
            _to_latin1(log.get("event_type", ""))[:28],
            _to_latin1(log.get("incident_id") or "")[:22],
            _to_latin1(log.get("entity_id") or "")[:20],
            _to_latin1(log.get("action") or "")[:18],
            _to_latin1(log.get("status", ""))[:14],
            _to_latin1(log.get("retry_count", "")),
            _to_latin1(log.get("reason") or log.get("error_details") or "")[:50],
        ]
        pdf.set_fill_color(239, 246, 255) if fill else pdf.set_fill_color(255, 255, 255)
        for i, cell in enumerate(row):
            pdf.cell(col_widths[i], 6, cell, border=1, fill=True)
        pdf.ln()
        fill = not fill

    # Summary section
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 8, "Summary Statistics", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    statuses = {}
    workflows = {}
    for log in logs:
        s = _to_latin1(log.get("status", "UNKNOWN"))
        w = _to_latin1(log.get("workflow", "UNKNOWN"))
        statuses[s] = statuses.get(s, 0) + 1
        workflows[w] = workflows.get(w, 0) + 1
    for k, v in sorted(statuses.items()):
        pdf.cell(0, 5, f"  Status {k}: {v} events", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for k, v in sorted(workflows.items(), key=lambda x: -x[1]):
        pdf.cell(0, 5, f"  Workflow {k}: {v} events", new_x="LMARGIN", new_y="NEXT")

    pdf_bytes = bytes(pdf.output())
    safe_suffix = f"_{incident_id}" if incident_id else ""
    filename = f"audit_trail{safe_suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
