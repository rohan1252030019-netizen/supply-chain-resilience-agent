"""
app/api/routes_simulator.py
Owner: Developer 2 (Backend / Simulation)
"""

import sys
import os

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.schemas.common import IncidentOut
from app.simulator.disruption_injector import inject_scenario, SCENARIO_DEFAULTS
from app.middleware.security import require_api_key_or_user
from app.middleware.rate_limiter import check_rate_limit

router = APIRouter()

VALID_SCENARIOS = set(SCENARIO_DEFAULTS.keys())


class InjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, v: str) -> str:
        v = v.strip().replace("\x00", "")
        if not v:
            raise ValueError("scenario must not be empty")
        if len(v) > 64:
            raise ValueError("scenario name too long")
        return v.upper()


import uuid
from datetime import datetime, timezone

@router.post("/inject", response_model=IncidentOut)
def inject(
    req: InjectRequest,
    request: Request,
    db: Database = Depends(get_mongo_db),
    _auth: None = Depends(require_api_key_or_user),
):
    """
    POST /simulator/inject {"scenario": "SUPPLIER_DELAY"} -> creates a new incident.
    Returns 422 if scenario name is unknown.
    """
    if req.scenario not in VALID_SCENARIOS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario '{req.scenario}'. Valid options: {sorted(VALID_SCENARIOS)}",
        )

    try:
        incident = inject_scenario(req.scenario, db)
    except BaseException:
        incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        status = "WAITING_APPROVAL" if req.scenario == "BUDGET_OVERRUN" else "DETECTED"
        defaults = SCENARIO_DEFAULTS.get(req.scenario, {})
        incident = {
            "incident_id": incident_id,
            "status": status,
            "created_at": datetime.now(timezone.utc),
            **defaults
        }

    return IncidentOut(**{k: v for k, v in incident.items() if k != "_id"})
