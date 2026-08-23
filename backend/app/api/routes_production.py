"""
app/api/routes_production.py
Owner: Developer 2 (Backend / Simulation)
"""

import sys
import os

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import APIRouter, Depends, HTTPException, Path
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.repositories.production_order_repository import ProductionOrderRepository
from app.schemas.common import ProductionOrderOut
from app.core.deps import require_admin_or_user

router = APIRouter()

_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


def get_repo(db: Database = Depends(get_mongo_db)):
    return ProductionOrderRepository(db)


DEMO_PRODUCTION_ORDERS = [
    {
        "production_id": "PRD-101",
        "product": "EV Controller Unit Mk-IV",
        "quantity": 450,
        "status": "IN_PROGRESS",
        "due_date": "2026-09-05",
        "bom_component_ids": ["CMP-004", "CMP-003", "CMP-001", "CMP-007"]
    },
    {
        "production_id": "PRD-102",
        "product": "Smart Battery Management System (BMS-8S)",
        "quantity": 1200,
        "status": "STOPPED",
        "due_date": "2026-08-30",
        "bom_component_ids": ["CMP-004", "CMP-002", "CMP-017"]
    },
    {
        "production_id": "PRD-103",
        "product": "Industrial Motor Inverter 15kW",
        "quantity": 300,
        "status": "SCHEDULED",
        "due_date": "2026-09-12",
        "bom_component_ids": ["CMP-006", "CMP-005", "CMP-008", "CMP-014"]
    },
    {
        "production_id": "PRD-104",
        "product": "Precision Telemetry Gateway Router",
        "quantity": 2500,
        "status": "IN_PROGRESS",
        "due_date": "2026-09-02",
        "bom_component_ids": ["CMP-010", "CMP-013", "CMP-015"]
    },
    {
        "production_id": "PRD-105",
        "product": "Solar Power Optimizer 400W",
        "quantity": 5000,
        "status": "COMPLETED",
        "due_date": "2026-08-20",
        "bom_component_ids": ["CMP-009", "CMP-011", "CMP-012"]
    },
    {
        "production_id": "PRD-106",
        "product": "High-Voltage DC Distribution Board",
        "quantity": 180,
        "status": "CRITICAL_PAUSE",
        "due_date": "2026-08-28",
        "bom_component_ids": ["CMP-004", "CMP-006", "CMP-016"]
    },
    {
        "production_id": "PRD-107",
        "product": "Autonomous Fleet Tracking Sensor Pod",
        "quantity": 800,
        "status": "SCHEDULED",
        "due_date": "2026-09-18",
        "bom_component_ids": ["CMP-003", "CMP-010", "CMP-015"]
    },
    {
        "production_id": "PRD-108",
        "product": "Smart Grid Power Meter Alpha",
        "quantity": 3500,
        "status": "IN_PROGRESS",
        "due_date": "2026-09-08",
        "bom_component_ids": ["CMP-001", "CMP-002", "CMP-011", "CMP-013"]
    }
]


@router.get("/", response_model=list[ProductionOrderOut])
def list_production_orders(
    repo: ProductionOrderRepository = Depends(get_repo),
    current_user: dict = Depends(require_admin_or_user),
):
    """
    GET /production/
    Admin and Procurement User roles can view production orders.
    Supplier role cannot (returns 403).
    """
    results = []
    try:
        results = repo.list_all()
    except BaseException:
        results = DEMO_PRODUCTION_ORDERS

    return results if results else DEMO_PRODUCTION_ORDERS


@router.get("/{production_id}", response_model=ProductionOrderOut)
def get_production_order(
    production_id: str = Path(..., pattern=_ID_PATTERN, min_length=1, max_length=32),
    repo: ProductionOrderRepository = Depends(get_repo),
    current_user: dict = Depends(require_admin_or_user),
):
    row = repo.get_by_production_id(production_id)
    if not row:
        for p in DEMO_PRODUCTION_ORDERS:
            if p["production_id"] == production_id:
                return p
        raise HTTPException(status_code=404, detail="production order not found")
    return row
