"""
app/schemas/common.py
Owner: Shared — Developer 2 maintains, but ALL devs read this before changing shapes.

These are the Pydantic (request/response) models frontend (Dev4) and agent (Dev1) code
against. If you need a new field, add it here FIRST and announce it in the team channel
so nobody's local branch silently diverges. This file mirrors docs/API_CONTRACTS.md —
keep them in sync.
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    component_id: str
    current_stock: int
    usable_stock: int
    daily_usage: float
    safety_stock: int
    days_of_supply: Optional[float] = None  # computed field, filled by decision_engine


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    supplier_id: str
    name: str
    quality_score: Optional[float] = None
    reliability_score: Optional[float] = None
    certifications: Optional[str] = None
    min_order_qty: Optional[int] = None


class ProductionOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    production_id: str
    product: str
    component_id: str
    quantity: int
    component_per_unit: int
    deadline: Optional[datetime] = None
    priority: str
    status: str


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    incident_id: str
    type: str
    severity: str
    affected_component: Optional[str] = None
    affected_po: Optional[str] = None
    status: str
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    timestamp: datetime
    incident_id: Optional[str] = None
    action: str
    tool: Optional[str] = None
    result: Optional[str] = None
    decision: Optional[str] = None
    reason: Optional[str] = None


class SupplierMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    supplier_id: str
    po_id: Optional[str] = None
    message: str
    timestamp: datetime
