import uuid
from datetime import datetime, timezone
from pymongo.database import Database

SCENARIO_DEFAULTS = {
    "SUPPLIER_DELAY": {"type": "SUPPLIER_DELAY", "severity": "CRITICAL",
                        "affected_component": "COMP-104", "affected_po": "PO-7712"},
    "STALE_INVENTORY": {"type": "STALE_INVENTORY", "severity": "MEDIUM",
                         "affected_component": "COMP-104", "affected_po": None},
    "SUPPLIER_LIE": {"type": "SUPPLIER_LIE", "severity": "HIGH",
                      "affected_component": "COMP-104", "affected_po": "PO-7712"},
    "QUALITY_FAILURE": {"type": "QUALITY_FAILURE", "severity": "HIGH",
                         "affected_component": "COMP-104", "affected_po": "PO-7712"},
    "BUDGET_OVERRUN": {"type": "BUDGET_OVERRUN", "severity": "CRITICAL",
                        "affected_component": "COMP-104", "affected_po": "PO-7712"},
}


def inject_scenario(scenario: str, db: Database) -> dict:
    """
    Creates a new Incident row for the given scenario and seeds recovery plan & audit log.
    For BUDGET_OVERRUN / Autonomous Threshold Escalation:
      - Sets status = WAITING_APPROVAL
      - Creates Recovery Plan costing ₹93,000 (exceeding ₹50,000 threshold)
    """
    defaults = SCENARIO_DEFAULTS[scenario]
    incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
    status = "WAITING_APPROVAL" if scenario == "BUDGET_OVERRUN" else "DETECTED"

    incident = {
        "incident_id": incident_id,
        "status": status,
        "created_at": datetime.now(timezone.utc),
        **defaults
    }
    try:
        db["incidents"].insert_one(incident)
    except Exception:
        pass

    # For BUDGET_OVERRUN, automatically seed a Recovery Plan exceeding threshold
    if scenario == "BUDGET_OVERRUN":
        plan = {
            "incident_id": incident_id,
            "approval_threshold_usd": 50000,
            "recommended_option_id": "A",
            "recommendation_reason": "Expedited air-freight batch from secondary vendor SUP-002 prevents line stoppage, but total cost ₹93,000 exceeds ₹50,000 limit.",
            "requires_human_approval": True,
            "options": [
                {
                    "option_id": "A",
                    "total_cost": 93000,
                    "max_delivery_days": 7,
                    "constraints_satisfied": True,
                    "allocation": {"SUP-002": 1000}
                },
                {
                    "option_id": "B",
                    "total_cost": 45000,
                    "max_delivery_days": 21,
                    "constraints_satisfied": False,
                    "rejection_reason": "21-day lead time exceeds assembly runway limit of 5 days"
                }
            ],
            "created_at": datetime.now(timezone.utc)
        }
        try:
            db["recovery_plans"].insert_one(plan)
        except Exception:
            pass
        try:
            db["audit_logs"].insert_one({
                "timestamp": datetime.now(timezone.utc),
                "incident_id": incident_id,
                "action": "Recovery plan generated costing ₹93,000. Exceeds ₹50,000 threshold; escalated to Executive Governance & Approvals.",
                "decision": "WAITING_APPROVAL"
            })
        except Exception:
            pass

    # Register lie scenario so simulator returns contradicting data
    if scenario == "SUPPLIER_LIE" and incident["affected_po"]:
        try:
            from app.simulator.supplier_simulator import register_supplier_lie
            register_supplier_lie(incident["affected_po"])
        except Exception:
            pass

    return incident
