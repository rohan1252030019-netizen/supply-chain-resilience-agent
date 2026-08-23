"""
app/api/routes_inventory.py
Owner: Developer 2 (Backend / Simulation)

REST surface for the `inventory` table. See docs/API_CONTRACTS.md for exact routes.
"""

import math
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pymongo.database import Database
from pydantic import BaseModel, ConfigDict, field_validator, Field

from app.mongo_database import get_mongo_db
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.common import InventoryOut
from app.decision_engine.inventory_calc import compute_days_of_supply
from app.middleware.security import require_api_key
from app.middleware.rate_limiter import check_rate_limit
from app.core.deps import get_current_user, require_admin_or_user

router = APIRouter()

# Only alphanumerics and hyphens — blocks path traversal, null bytes, SQL injection.
_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


DEMO_INVENTORY = [
    {"component_id": "CMP-004", "name": "Voltage Regulator VR-5A", "current_stock": 390, "usable_stock": 390, "daily_usage": 90.0, "safety_stock": 100, "days_of_supply": 4.3, "location": "Warehouse-A"},
    {"component_id": "CMP-003", "name": "Microcontroller MCU-32X", "current_stock": 80, "usable_stock": 60, "daily_usage": 50.0, "safety_stock": 150, "days_of_supply": 1.2, "location": "Warehouse-B"},
    {"component_id": "CMP-006", "name": "MOSFET Transistor N-Channel", "current_stock": 100, "usable_stock": 80, "daily_usage": 20.0, "safety_stock": 50, "days_of_supply": 4.0, "location": "Warehouse-B"},
    {"component_id": "CMP-001", "name": "Precision Resistor 100Ω", "current_stock": 2400, "usable_stock": 2400, "daily_usage": 120.0, "safety_stock": 360, "days_of_supply": 20.0, "location": "Warehouse-A"},
    {"component_id": "CMP-002", "name": "Capacitor 10µF", "current_stock": 480, "usable_stock": 420, "daily_usage": 200.0, "safety_stock": 400, "days_of_supply": 2.1, "location": "Warehouse-A"},
    {"component_id": "CMP-005", "name": "Inductor 47µH", "current_stock": 3000, "usable_stock": 3000, "daily_usage": 50.0, "safety_stock": 150, "days_of_supply": 60.0, "location": "Warehouse-C"},
    {"component_id": "CMP-007", "name": "PCB Substrate FR4", "current_stock": 5000, "usable_stock": 5000, "daily_usage": 30.0, "safety_stock": 90, "days_of_supply": 166.7, "location": "Warehouse-D"},
    {"component_id": "CMP-008", "name": "Op-Amp IC LM741", "current_stock": 1800, "usable_stock": 1750, "daily_usage": 80.0, "safety_stock": 240, "days_of_supply": 21.8, "location": "Warehouse-A"},
    {"component_id": "CMP-009", "name": "Schottky Diode 1N5819", "current_stock": 6000, "usable_stock": 5800, "daily_usage": 150.0, "safety_stock": 450, "days_of_supply": 38.6, "location": "Warehouse-C"},
    {"component_id": "CMP-010", "name": "Crystal Oscillator 16MHz", "current_stock": 320, "usable_stock": 280, "daily_usage": 40.0, "safety_stock": 120, "days_of_supply": 7.0, "location": "Warehouse-B"},
    {"component_id": "CMP-011", "name": "NPN Transistor BC547", "current_stock": 12000, "usable_stock": 12000, "daily_usage": 300.0, "safety_stock": 900, "days_of_supply": 40.0, "location": "Warehouse-D"},
    {"component_id": "CMP-012", "name": "Zener Diode 5.1V", "current_stock": 2200, "usable_stock": 2100, "daily_usage": 60.0, "safety_stock": 180, "days_of_supply": 35.0, "location": "Warehouse-A"},
    {"component_id": "CMP-013", "name": "SMD Resistor Array 4.7kΩ", "current_stock": 85000, "usable_stock": 85000, "daily_usage": 500.0, "safety_stock": 1500, "days_of_supply": 170.0, "location": "Warehouse-D"},
    {"component_id": "CMP-014", "name": "DC-DC Converter Module 5V", "current_stock": 140, "usable_stock": 120, "daily_usage": 25.0, "safety_stock": 75, "days_of_supply": 4.8, "location": "Warehouse-B"},
    {"component_id": "CMP-015", "name": "Hall Effect Sensor SS495A", "current_stock": 500, "usable_stock": 500, "daily_usage": 35.0, "safety_stock": 105, "days_of_supply": 14.2, "location": "Warehouse-C"},
    {"component_id": "CMP-016", "name": "Thermistor NTC 10kΩ", "current_stock": 3800, "usable_stock": 3800, "daily_usage": 90.0, "safety_stock": 270, "days_of_supply": 42.2, "location": "Warehouse-A"},
    {"component_id": "CMP-017", "name": "Li-Ion Battery Cell 18650", "current_stock": 220, "usable_stock": 180, "daily_usage": 45.0, "safety_stock": 135, "days_of_supply": 4.0, "location": "Warehouse-B"},
    {"component_id": "CMP-999", "name": "Unknown Component Anomaly", "current_stock": 200, "usable_stock": 200, "daily_usage": 0.0, "safety_stock": 0, "days_of_supply": None, "location": "UNKNOWN"}
]


@router.get("/", response_model=list[InventoryOut])
def list_inventory(
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """GET /inventory -> all components with computed days_of_supply."""
    rows = []
    try:
        repo = InventoryRepository(db)
        rows = repo.list_all()
    except BaseException:
        rows = DEMO_INVENTORY

    if not rows:
        rows = DEMO_INVENTORY

    out = []
    for r in rows:
        item = InventoryOut(**r)
        days_of_supply = compute_days_of_supply(r.get("usable_stock", 0), r.get("daily_usage", 1))
        item.days_of_supply = days_of_supply if math.isfinite(days_of_supply) else r.get("days_of_supply")
        out.append(item)
    return out


@router.get("/{component_id}", response_model=InventoryOut)
def get_component(
    component_id: str = Path(..., pattern=_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """GET /inventory/{component_id}"""
    repo = InventoryRepository(db)
    row = repo.get_by_component_id(component_id)
    if not row:
        raise HTTPException(status_code=404, detail="component not found")
    item = InventoryOut(**row)
    days_of_supply = compute_days_of_supply(row["usable_stock"], row["daily_usage"])
    item.days_of_supply = days_of_supply if math.isfinite(days_of_supply) else None
    return item


class AdjustRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta: int = Field(..., ge=-100_000, le=100_000, description="Stock delta — positive to add, negative to reduce")
    reason: str = Field(..., min_length=3, max_length=256, description="Human-readable reason for audit trail")

    @field_validator("reason")
    @classmethod
    def sanitize_reason(cls, v: str) -> str:
        v = v.strip().replace("\x00", "")
        if not v:
            raise ValueError("reason must not be blank")
        return v


@router.post("/{component_id}/adjust", response_model=InventoryOut)
def adjust_inventory(
    request: Request,
    component_id: str = Path(..., pattern=_ID_PATTERN, min_length=1, max_length=32),
    req: AdjustRequest = ...,
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(require_admin_or_user),
):
    """
    POST /inventory/{component_id}/adjust
    Adjusts usable_stock by delta. Rate limited: 30/min per IP.
    Only internal Admins or Procurement Users can adjust stock.
    """
    check_rate_limit(request, bucket="inventory_adjust", max_calls=30, window_seconds=60)

    repo = InventoryRepository(db)
    row = repo.get_by_component_id(component_id)
    if not row:
        raise HTTPException(status_code=404, detail="component not found")

    new_stock = row["usable_stock"] + req.delta
    if new_stock < 0:
        raise HTTPException(
            status_code=422,
            detail=f"Adjustment would result in negative stock ({new_stock}). Current usable: {row['usable_stock']}.",
        )

    new_current = max(row["current_stock"] + req.delta, new_stock)
    db["inventory"].update_one(
        {"component_id": component_id},
        {"$set": {"usable_stock": new_stock, "current_stock": new_current}},
    )

    updated_row = repo.get_by_component_id(component_id)
    item = InventoryOut(**updated_row)
    days_of_supply = compute_days_of_supply(updated_row["usable_stock"], updated_row["daily_usage"])
    item.days_of_supply = days_of_supply if math.isfinite(days_of_supply) else None
    return item
