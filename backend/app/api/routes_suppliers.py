"""
app/api/routes_suppliers.py
Owner: Developer 2 (Backend / Simulation)
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Optional
from pymongo.database import Database

from app.mongo_database import get_mongo_db
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.common import SupplierOut, SupplierMessageOut
from app.core.deps import get_current_user

router = APIRouter()

_SUPPLIER_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


def get_repo(db: Database = Depends(get_mongo_db)):
    return SupplierRepository(db)


def _resolve_supplier_id(current_user: dict, db: Database) -> Optional[str]:
    supplier_id = current_user.get("supplier_id")
    if supplier_id:
        return supplier_id
    email = current_user.get("email")
    if email:
        supp = db["suppliers"].find_one({"contact_email": email.lower()})
        if supp:
            return supp.get("supplier_id")
    user_id = current_user.get("user_id")
    if user_id:
        supp = db["suppliers"].find_one({"user_id": user_id})
        if supp:
            return supp.get("supplier_id")
    return None


DEMO_SUPPLIERS = [
    {"supplier_id": "SUP-001", "name": "Meridian Electro Components Pvt. Ltd.", "contact_email": "orders@meridianelectro.in", "quality_score": 88, "reliability_score": 72, "on_time_delivery_rate": 0.68, "certifications": "ISO9001", "lead_time_days": 14, "min_order_qty": 100, "country": "India", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-002", "name": "Bergmann Precision Supplies GmbH", "contact_email": "supply@bergmann-precision.de", "quality_score": 95, "reliability_score": 91, "on_time_delivery_rate": 0.94, "certifications": "ISO9001,RoHS", "lead_time_days": 7, "min_order_qty": 50, "country": "Germany", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-003", "name": "Swift Circuit Supply Pte Ltd", "contact_email": "urgent@swiftcircuit.sg", "quality_score": 80, "reliability_score": 85, "on_time_delivery_rate": 0.88, "certifications": "RoHS", "lead_time_days": 3, "min_order_qty": 200, "country": "Singapore", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-004", "name": "Hongwei Bulk Electronics Co., Ltd.", "contact_email": "sales@hongweibulk.cn", "quality_score": 70, "reliability_score": 62, "on_time_delivery_rate": 0.60, "certifications": "", "lead_time_days": 21, "min_order_qty": 500, "country": "China", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-005", "name": "Van Dijk Fast-Track Supply B.V.", "contact_email": "vip@vandijksupply.eu", "quality_score": 93, "reliability_score": 96, "on_time_delivery_rate": 0.97, "certifications": "ISO9001,RoHS,IATF16949", "lead_time_days": 5, "min_order_qty": 100, "country": "Netherlands", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-006", "name": "Fuxin Discount Parts Co.", "contact_email": "info@fuxindiscount.cn", "quality_score": 55, "reliability_score": 40, "on_time_delivery_rate": 0.35, "certifications": "", "lead_time_days": 30, "min_order_qty": 1000, "country": "China", "status": "SUSPENDED", "blacklisted": True},
    {"supplier_id": "SUP-007", "name": "Nova Emerging Components Pvt Ltd", "contact_email": "hello@novaemerging.in", "quality_score": 78, "reliability_score": None, "on_time_delivery_rate": None, "certifications": "ISO9001", "lead_time_days": 10, "min_order_qty": 100, "country": "India", "status": "UNDER_EVALUATION", "blacklisted": False},
    {"supplier_id": "SUP-008", "name": "Taihe Mass Production Co., Ltd.", "contact_email": "bulk@taihemass.tw", "quality_score": 82, "reliability_score": 78, "on_time_delivery_rate": 0.75, "certifications": "ISO9001,RoHS", "lead_time_days": 28, "min_order_qty": 2000, "country": "Taiwan", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-009", "name": "Kaida Semiconductor Ltd.", "contact_email": "sales@kaida-semi.jp", "quality_score": 92, "reliability_score": 89, "on_time_delivery_rate": 0.91, "certifications": "ISO9001,RoHS,IATF16949", "lead_time_days": 10, "min_order_qty": 250, "country": "Japan", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-010", "name": "Ridgeline Circuit Works Inc.", "contact_email": "procurement@ridgelinecircuit.us", "quality_score": 85, "reliability_score": 80, "on_time_delivery_rate": 0.82, "certifications": "ISO9001", "lead_time_days": 12, "min_order_qty": 150, "country": "USA", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-011", "name": "Falkenstein Elektronik GmbH", "contact_email": "orders@falkenstein-elektronik.de", "quality_score": 91, "reliability_score": 87, "on_time_delivery_rate": 0.90, "certifications": "ISO9001,RoHS", "lead_time_days": 8, "min_order_qty": 100, "country": "Germany", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-012", "name": "Hanbit Components Korea Co., Ltd.", "contact_email": "supply@hanbitcomp.kr", "quality_score": 87, "reliability_score": 84, "on_time_delivery_rate": 0.86, "certifications": "ISO9001,RoHS", "lead_time_days": 9, "min_order_qty": 200, "country": "South Korea", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-013", "name": "Marina Micro Systems Pte Ltd", "contact_email": "info@marinamicro.sg", "quality_score": 76, "reliability_score": 71, "on_time_delivery_rate": 0.73, "certifications": "RoHS", "lead_time_days": 15, "min_order_qty": 300, "country": "Singapore", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-014", "name": "Ashford Technologies Ltd", "contact_email": "orders@ashfordtech.co.uk", "quality_score": 89, "reliability_score": 83, "on_time_delivery_rate": 0.85, "certifications": "ISO9001,IATF16949", "lead_time_days": 11, "min_order_qty": 75, "country": "UK", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-015", "name": "Suryan Power Supplies Pvt Ltd", "contact_email": "sales@suryanpower.in", "quality_score": 83, "reliability_score": 79, "on_time_delivery_rate": 0.80, "certifications": "ISO9001", "lead_time_days": 16, "min_order_qty": 50, "country": "India", "status": "ACTIVE", "blacklisted": False},
    {"supplier_id": "SUP-016", "name": "Chunghua Passive Components Co.", "contact_email": "sales@chunghuapassive.tw", "quality_score": 79, "reliability_score": 76, "on_time_delivery_rate": 0.77, "certifications": "RoHS", "lead_time_days": 18, "min_order_qty": 500, "country": "Taiwan", "status": "ACTIVE", "blacklisted": False}
]


@router.get("/", response_model=list[SupplierOut])
def list_suppliers(
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """
    GET /suppliers/
    Admin and User roles can see all suppliers.
    Supplier role can only see themselves.
    """
    results = []
    try:
        repo = SupplierRepository(db)
        if current_user["role"] == "supplier":
            supplier_id = _resolve_supplier_id(current_user, db)
            if not supplier_id:
                return [DEMO_SUPPLIERS[0]]
            single = repo.get_by_supplier_id(supplier_id)
            return [single] if single else [DEMO_SUPPLIERS[0]]
        results = repo.list_all()
    except BaseException:
        results = DEMO_SUPPLIERS

    return results if results else DEMO_SUPPLIERS


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: str = Path(..., pattern=_SUPPLIER_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """
    GET /suppliers/{supplier_id}
    Enforces that suppliers can only request their own details.
    """
    repo = SupplierRepository(db)
    if current_user["role"] == "supplier":
        resolved_id = _resolve_supplier_id(current_user, db)
        if supplier_id != resolved_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this supplier")

    row = repo.get_by_supplier_id(supplier_id)
    if not row:
        raise HTTPException(status_code=404, detail="supplier not found")
    return row


@router.get("/{supplier_id}/messages", response_model=List[SupplierMessageOut])
def get_supplier_messages(
    supplier_id: str = Path(..., pattern=_SUPPLIER_ID_PATTERN, min_length=1, max_length=32),
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """
    GET /suppliers/{supplier_id}/messages
    Returns all messages exchanged with this supplier.
    Enforces that suppliers can only request their own messages.
    """
    if current_user["role"] == "supplier":
        resolved_id = _resolve_supplier_id(current_user, db)
        if supplier_id != resolved_id:
            raise HTTPException(status_code=403, detail="Not authorized to access these messages")

    supplier = SupplierRepository(db).get_by_supplier_id(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="supplier not found")

    return list(db["supplier_messages"].find({"supplier_id": supplier_id}, {"_id": 0}).sort("timestamp", 1))
