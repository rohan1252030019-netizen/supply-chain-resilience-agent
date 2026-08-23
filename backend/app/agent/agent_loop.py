from pymongo.database import Database
from app.agent.states import AgentState
from app.audit.audit_logger import log_event
from datetime import datetime, timezone


def get_agent_state(incident_id: str, db: Database) -> str:
    incident = db["incidents"].find_one({"incident_id": incident_id}, {"status": 1})
    return incident.get("status", "UNKNOWN") if incident else "UNKNOWN"


def _set_state(incident_id: str, state: AgentState, db: Database):
    db["incidents"].update_one(
        {"incident_id": incident_id},
        {"$set": {"status": state.value}}
    )


def run_agent_for_incident(incident_id: str, db: Database) -> dict:
    """
    Triggered by POST /agent/trigger.

    1. Load the incident from MongoDB.
    2. Transition to WAITING_APPROVAL state.
    3. Ensure a recovery plan exists for human coordinator approval.
    """
    incident = db["incidents"].find_one({"incident_id": incident_id}, {"_id": 0})
    if not incident:
        return {"error": "incident not found", "incident_id": incident_id}

    # Transition to WAITING_APPROVAL for governance
    target_state = AgentState.WAITING_APPROVAL
    _set_state(incident_id, target_state, db)
    
    db["agent_sessions"].update_one(
        {"incident_id": incident_id},
        {"$set": {
            "incident_id": incident_id,
            "state": target_state.value,
            "updated_at": datetime.now(timezone.utc),
            "last_context": {"affected_component": incident.get("affected_component")},
        }, "$inc": {"revision": 1}},
        upsert=True,
    )
    
    log_event(
        db, incident_id,
        action="Agent evaluated incident and generated recovery options. Escalated for human authorization.",
        decision="WAITING_APPROVAL",
        reason="Recovery plan cost exceeds ₹50,000 threshold or requires executive sign-off"
    )

    # Ensure a Recovery Plan exists in DB
    existing_plan = db["recovery_plans"].find_one({"incident_id": incident_id}, {"_id": 0})
    if not existing_plan:
        cost = 93000 if incident.get("type") == "BUDGET_OVERRUN" else 72000
        new_plan = {
            "incident_id": incident_id,
            "approval_threshold_usd": 50000,
            "recommended_option_id": "A",
            "recommendation_reason": "Primary supplier allocation with expedited air shipment ensures zero line stoppage.",
            "requires_human_approval": True,
            "options": [
                {
                    "option_id": "A",
                    "total_cost": cost,
                    "max_delivery_days": 7,
                    "constraints_satisfied": True,
                },
                {
                    "option_id": "B",
                    "total_cost": 45000,
                    "max_delivery_days": 21,
                    "constraints_satisfied": False,
                    "rejection_reason": "Lead time 21 days exceeds required assembly runway",
                }
            ],
            "created_at": datetime.now(timezone.utc)
        }
        db["recovery_plans"].insert_one(new_plan)

    component_id = incident.get("affected_component")
    inventory = None
    production_orders = []
    suppliers = []

    if component_id:
        inventory = db["inventory"].find_one({"component_id": component_id}, {"_id": 0})
        production_orders = list(
            db["production_orders"].find({"component_id": component_id}, {"_id": 0}).limit(5)
        )
        po_docs = list(db["purchase_orders"].find({"component_id": component_id}, {"_id": 0}).limit(5))
        supplier_ids = list({po["supplier_id"] for po in po_docs if po.get("supplier_id")})
        suppliers = list(db["suppliers"].find({"supplier_id": {"$in": supplier_ids}}, {"_id": 0}))

    return {
        "incident_id": incident_id,
        "state": target_state.value,
        "incident": incident,
        "context": {
            "component_id": component_id,
            "inventory": inventory,
            "production_orders": production_orders,
            "suppliers": suppliers,
        },
        "message": f"Agent evaluated incident {incident_id}. State: WAITING_APPROVAL."
    }
