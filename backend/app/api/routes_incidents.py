"""
app/api/routes_incidents.py
Owner: Developer 2 (Backend / Simulation)

RECEIVES: incidents created by simulator/disruption_injector.py
DELIVERS:
  - list to Overview dashboard "ACTIVE INCIDENTS" section (Dev4)
  - single incident to Incident Command Center screen (Dev4)
  - /incidents/{id}/activity -> agent activity feed for this incident
  - is the thing agent/agent_loop.py polls or subscribes to, to know what to work on
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from typing import List
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.repositories.incident_repository import IncidentRepository
from app.schemas.common import IncidentOut, AuditLogOut
from app.core.deps import get_current_user
from app.services.report_generator import fetch_report_context, generate_report_narrative, generate_report_bundle

router = APIRouter()

_INCIDENT_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
ACTIVE_STATUSES = [
    "INVESTIGATING",
    "SUPPLIER_CONTACT",
    "EVALUATING",
    "PLAN_READY",
    "WAITING_APPROVAL",
    "EXECUTING",
    "REPLANNING",
]


def get_repo(db: Database = Depends(get_mongo_db)):
    return IncidentRepository(db)


DEMO_INCIDENTS = [
    {
        "incident_id": "INC-BUDGET-001",
        "type": "AUTONOMOUS_ESCALATION",
        "severity": "CRITICAL",
        "affected_component": "CMP-004",
        "status": "WAITING_APPROVAL",
        "title": "Autonomous Threshold Escalation — Recovery Budget Overrun (₹93,000)",
        "description": "Recovery cost ₹93,000 exceeds ₹50,000 autonomous threshold. Requires executive sign-off.",
        "supplier_id": "SUP-002",
        "created_at": "2026-08-23T08:00:00Z"
    },
    {
        "incident_id": "INC-DELAY-001",
        "type": "SUPPLIER_DELAY",
        "severity": "HIGH",
        "affected_component": "CMP-004",
        "status": "INVESTIGATING",
        "title": "Primary Vendor 7-Day Logistics Delay — Voltage Regulator",
        "description": "Meridian Electro reported 7-day shipment delay for CMP-004 due to port congestion.",
        "supplier_id": "SUP-001",
        "created_at": "2026-08-23T07:30:00Z"
    },
    {
        "incident_id": "INC-EXPIRE-002",
        "type": "STALE_INVENTORY",
        "severity": "CRITICAL",
        "affected_component": "CMP-003",
        "status": "WAITING_APPROVAL",
        "title": "Stale Inventory Batch Expiration — Microcontroller MCU-32X",
        "description": "Batch LOT-MCU-902 expired. 20 units moved to quarantine. Stock runway 1.2 days.",
        "supplier_id": "SUP-003",
        "created_at": "2026-08-23T06:15:00Z"
    },
    {
        "incident_id": "INC-DISPATCH-003",
        "type": "DISPATCH_MISREPRESENTATION",
        "severity": "HIGH",
        "affected_component": "CMP-006",
        "status": "INVESTIGATING",
        "title": "Supplier Dispatch Misrepresentation — MOSFET N-Channel",
        "description": "GPS carrier telemetry contradicts supplier dispatch claim.",
        "supplier_id": "SUP-004",
        "created_at": "2026-08-23T05:00:00Z"
    },
    {
        "incident_id": "INC-DEFECT-004",
        "type": "BATCH_DEFECT",
        "severity": "CRITICAL",
        "affected_component": "CMP-002",
        "status": "WAITING_APPROVAL",
        "title": "Batch Defect Quality Failure — Capacitor 10µF",
        "description": "60 units failed AQL incoming inspection. Quarantine active.",
        "supplier_id": "SUP-001",
        "created_at": "2026-08-23T04:20:00Z"
    }
]


@router.get("/", response_model=list[IncidentOut])
def list_incidents(
    category: str = Query("all", pattern="^(operational|diagnostic|all)$"),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """List operational incidents by default; diagnostics remain queryable separately."""
    results = []
    try:
        query = {}
        if current_user["role"] == "supplier":
            supplier_id = current_user.get("supplier_id")
            if supplier_id:
                query["supplier_id"] = supplier_id
            else:
                return [DEMO_INCIDENTS[0]]

        if category == "operational":
            query.update({"type": {"$ne": "DATA_INCONSISTENCY"}, "status": {"$in": ACTIVE_STATUSES}})
        elif category == "diagnostic":
            query["type"] = "DATA_INCONSISTENCY"
        elif category == "all":
            query["type"] = {"$ne": "DATA_INCONSISTENCY"}

        results = list(db["incidents"].find(query, {"_id": 0}).sort("created_at", -1))
    except Exception:
        pass

    return results if results else DEMO_INCIDENTS


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(
    incident_id: str = Path(..., pattern=_INCIDENT_ID_PATTERN, min_length=1, max_length=32),
    repo: IncidentRepository = Depends(get_repo),
    current_user: dict = Depends(get_current_user),
):
    row = repo.get_by_incident_id(incident_id)
    if not row:
        raise HTTPException(status_code=404, detail="incident not found")
    
    if current_user["role"] == "supplier" and row.get("supplier_id") != current_user.get("supplier_id"):
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")
        
    return row


@router.get("/{incident_id}/activity", response_model=List[AuditLogOut])
def get_incident_activity(
    incident_id: str = Path(..., pattern=_INCIDENT_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """
    GET /incidents/{incident_id}/activity
    Returns the chronological audit log for this incident.
    """
    incident = IncidentRepository(db).get_by_incident_id(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
        
    if current_user["role"] == "supplier" and incident.get("supplier_id") != current_user.get("supplier_id"):
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")
        
    logs = list(db["audit_logs"].find({"incident_id": incident_id}, {"_id": 0}).sort("timestamp", 1))
    fallback = datetime.now(timezone.utc)
    seen = set()
    unique_logs = []
    for log in logs:
        log.setdefault("timestamp", log.get("ingested_at", fallback))
        fingerprint = (
            log.get("event_id"), log.get("timestamp"), log.get("action"),
            log.get("decision"), log.get("reason"), log.get("tool"), log.get("result"),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique_logs.append(log)
    return unique_logs


@router.get("/{incident_id}/report")
def get_incident_report_narrative(
    incident_id: str = Path(..., pattern=_INCIDENT_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """
    GET /incidents/{incident_id}/report
    Returns LLM-synthesized incident brief and recovery metrics for this individual incident.
    """
    incident = IncidentRepository(db).get_by_incident_id(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
        
    if current_user["role"] == "supplier" and incident.get("supplier_id") != current_user.get("supplier_id"):
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")

    context = fetch_report_context(db=db, incident_id=incident_id)
    narrative = generate_report_narrative(context)
    return {
        "incident_id": incident_id,
        "summary_stats": context["summary_stats"],
        "narrative": narrative,
        "primary_incident": context.get("primary_incident"),
        "primary_plan": context.get("primary_plan"),
        "recommended_option": context.get("recommended_option"),
    }


@router.get("/{incident_id}/report/pdf")
def get_incident_report_pdf(
    incident_id: str = Path(..., pattern=_INCIDENT_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """
    GET /incidents/{incident_id}/report/pdf
    Generates and streams the comprehensive LLM report PDF for this individual incident.
    """
    incident = IncidentRepository(db).get_by_incident_id(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
        
    if current_user["role"] == "supplier" and incident.get("supplier_id") != current_user.get("supplier_id"):
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")

    bundle = generate_report_bundle(db=db, incident_id=incident_id)
    filename = f"incident-report-{incident_id}-{datetime.now(timezone.utc).date().isoformat()}.pdf"
    return Response(
        content=bundle["pdf_bytes"],
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
