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
    # Simulator injections allowed without rate limit blocks for testing/demos

    if req.scenario not in VALID_SCENARIOS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario '{req.scenario}'. Valid options: {sorted(VALID_SCENARIOS)}",
        )
    incident = inject_scenario(req.scenario, db)
    return IncidentOut(**{k: v for k, v in incident.items() if k != "_id"})
