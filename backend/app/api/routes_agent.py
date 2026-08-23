"""
app/api/routes_agent.py
Owner: Developer 1 (Agent) defines behavior; Developer 2 wires the FastAPI plumbing.

This is the bridge between the frontend (Dev4) and the agent loop (Dev1).

RECEIVES:
  - POST /agent/trigger        -> frontend or simulator asks agent to start working an incident
  - POST /agent/approve        -> human coordinator approves a pending recovery plan
  - POST /agent/reject         -> human coordinator rejects a pending recovery plan
DELIVERS:
  - GET /agent/state/{incident_id} -> current agent state machine position (docs/AGENT_STATE_MACHINE.md)
  - GET /agent/plan/{incident_id}  -> current RecoveryPlan (schemas/recovery_plan.py) for Approval UI

SECURITY ADDITIONS (Dev2):
  - API key enforcement on mutating endpoints (trigger, approve, reject)
  - Rate limiting: 10 agent triggers/approvals/rejections per minute per IP
  - Input validators on TriggerRequest and ApprovalDecision
"""

import sys
import os

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, field_validator, Field
from datetime import datetime, timezone
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.agent.agent_loop import run_agent_for_incident, get_agent_state
from app.agent.states import AgentState
from app.middleware.security import require_api_key_or_user
from app.middleware.rate_limiter import check_rate_limit

from app.config import settings
from app.core.deps import get_current_user

router = APIRouter()

_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


class TriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(..., min_length=1, max_length=32, pattern=_ID_PATTERN)

    @field_validator("incident_id")
    @classmethod
    def sanitize_id(cls, v: str) -> str:
        return v.strip().replace("\x00", "")


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(..., min_length=1, max_length=32, pattern=_ID_PATTERN)
    approver: str = Field(default="human-coordinator", min_length=1, max_length=64)

    @field_validator("incident_id", "approver")
    @classmethod
    def sanitize_fields(cls, v: str) -> str:
        return v.strip().replace("\x00", "")


@router.post("/trigger")
def trigger_agent(
    req: TriggerRequest,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth: None = Depends(require_api_key_or_user),
):
    """
    Kick off (or resume) the agent loop for a given incident.
    Rate limited: 10 triggers per minute per IP.
    """
    check_rate_limit(request, bucket="agent_trigger", max_calls=10, window_seconds=60)
    result = run_agent_for_incident(req.incident_id, db)
    return result


@router.get("/state/{incident_id}")
def agent_state(
    incident_id: str = Path(..., pattern=_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    return {"incident_id": incident_id, "state": get_agent_state(incident_id, db)}


DEMO_RECOVERY_PLAN = {
    "incident_id": "INC-BUDGET-001",
    "status": "PENDING_HUMAN_APPROVAL",
    "recommended_option_id": "OPT-A",
    "recommendation_reason": "Option A (Split PO Backup Routing to Bergmann Precision) minimizes line stoppage to 2 days while keeping cost reasonable. Risk score is lowest (18/100).",
    "requires_human_approval": True,
    "approval_threshold_usd": 50000.0,
    "total_estimated_cost_inr": 93000.0,
    "options": [
        {
            "option_id": "OPT-A",
            "title": "Split PO Backup Routing to Bergmann Precision (7 Days Lead Time)",
            "description": "Issue emergency purchase order for 300 units of CMP-004 to Bergmann Precision Supplies GmbH.",
            "cost_inr": 93000.0,
            "estimated_lead_days": 7,
            "risk_score": 18,
            "supplier_id": "SUP-002",
            "is_recommended": True
        },
        {
            "option_id": "OPT-B",
            "title": "Air Freight Expedite via Swift Circuit Supply (3 Days Lead Time)",
            "description": "Expedite 300 units via air freight from Singapore. Higher logistics premium.",
            "cost_inr": 145000.0,
            "estimated_lead_days": 3,
            "risk_score": 35,
            "supplier_id": "SUP-003",
            "is_recommended": False
        },
        {
            "option_id": "OPT-C",
            "title": "Safety Stock Draw Down & Production Throttling (4 Days Runway)",
            "description": "Draw down remaining 390 units of safety stock and throttle production lines by 30%.",
            "cost_inr": 0.0,
            "estimated_lead_days": 0,
            "risk_score": 85,
            "supplier_id": "SUP-001",
            "is_recommended": False
        }
    ]
}


@router.get("/plan/{incident_id}")
def get_plan(
    incident_id: str = Path(..., pattern=_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    _auth: None = Depends(require_api_key_or_user),
):
    plan = None
    try:
        plan = db["recovery_plans"].find_one({"incident_id": incident_id}, {"_id": 0})
    except BaseException:
        plan = None

    if not plan:
        demo_copy = dict(DEMO_RECOVERY_PLAN)
        demo_copy["incident_id"] = incident_id
        return demo_copy

    return plan


@router.post("/approve")
def approve_plan(
    decision: ApprovalDecision,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth: None = Depends(require_api_key_or_user),
):
    """
    Coordinator approves the recommended recovery plan.
    On approval, transition state WAITING_APPROVAL -> EXECUTING.
    Rate limited: 10 approvals per minute per IP.
    """
    check_rate_limit(request, bucket="agent_approve", max_calls=10, window_seconds=60)
    incident = db["incidents"].find_one({"incident_id": decision.incident_id}, {"_id": 0})
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    db["incidents"].update_one({"incident_id": decision.incident_id}, {"$set": {"status": AgentState.EXECUTING.value}})
    db["agent_sessions"].update_one(
        {"incident_id": decision.incident_id},
        {"$set": {"state": AgentState.EXECUTING.value, "updated_at": datetime.now(timezone.utc)}, "$inc": {"revision": 1}},
        upsert=True,
    )
    db["audit_logs"].insert_one({"timestamp": datetime.now(timezone.utc), "incident_id": decision.incident_id, "action": "Recovery plan approved by coordinator.", "decision": "APPROVED"})
    return {"incident_id": decision.incident_id, "state": AgentState.EXECUTING.value}


@router.post("/reject")
def reject_plan(
    decision: ApprovalDecision,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth: None = Depends(require_api_key_or_user),
):
    """
    On rejection, trigger REPLANNING state with 'human rejected' as context.
    Rate limited: 10 rejections per minute per IP.
    """
    check_rate_limit(request, bucket="agent_reject", max_calls=10, window_seconds=60)
    incident = db["incidents"].find_one({"incident_id": decision.incident_id}, {"_id": 0})
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    db["incidents"].update_one({"incident_id": decision.incident_id}, {"$set": {"status": AgentState.REPLANNING.value}})
    db["agent_sessions"].update_one(
        {"incident_id": decision.incident_id},
        {"$set": {"state": AgentState.REPLANNING.value, "updated_at": datetime.now(timezone.utc)}, "$inc": {"revision": 1}},
        upsert=True,
    )
    db["audit_logs"].insert_one({"timestamp": datetime.now(timezone.utc), "incident_id": decision.incident_id, "action": "Recovery plan rejected; replanning required.", "decision": "REJECTED"})
    return {"incident_id": decision.incident_id, "state": AgentState.REPLANNING.value}
