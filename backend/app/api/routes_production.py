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
    return repo.list_all()


@router.get("/{production_id}", response_model=ProductionOrderOut)
def get_production_order(
    production_id: str = Path(..., pattern=_ID_PATTERN, min_length=1, max_length=32),
    repo: ProductionOrderRepository = Depends(get_repo),
    current_user: dict = Depends(require_admin_or_user),
):
    row = repo.get_by_production_id(production_id)
    if not row:
        raise HTTPException(status_code=404, detail="production order not found")
    return row
