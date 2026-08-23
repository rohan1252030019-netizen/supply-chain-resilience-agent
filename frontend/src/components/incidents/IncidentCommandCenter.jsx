/**
 * src/components/incidents/IncidentCommandCenter.jsx
 * Owner: Developer 4 (Frontend)
 *
 * RECEIVES: incidentId from the route
 * DELIVERS: POST /agent/trigger, /agent/approve, /agent/reject via user actions
 *           and comprehensive LLM operations report viewing + PDF download.
 */
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { getIncident, getIncidentActivity, getIncidentReport } from "../../api/incidents.js";
import { getAgentState, getAgentPlan, triggerAgent } from "../../api/agent.js";

import SeverityBadge from "../common/SeverityBadge.jsx";
import StatusBadge from "../common/StatusBadge.jsx";
import InfoCards from "./InfoCards.jsx";
import RecoveryPlanPanel from "./RecoveryPlanPanel.jsx";
import ApprovalModal from "./ApprovalModal.jsx";
import { downloadOperatorReport } from "../../api/reports.js";

const FLOW_STEPS = [
  { key: "DETECTED", label: "Disruption" },
  { key: "INVESTIGATING", label: "Investigation" },
  { key: "SUPPLIER_CONTACT", label: "Agent Actions" },
  { key: "EVALUATING", label: "Recovery Options" },
  { key: "PLAN_READY", label: "Decision" },
  { key: "WAITING_APPROVAL", label: "Approval" },
  { key: "EXECUTING", label: "ERP Update" },
  { key: "RESOLVED", label: "Audit" },
];
const FLOW_ORDER = FLOW_STEPS.map((s) => s.key);

export default function IncidentCommandCenter() {
  const { incidentId } = useParams();
  const [incident, setIncident] = useState(null);
  const [agentState, setAgentState] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [plan, setPlan] = useState(null);
  const [triggerError, setTriggerError] = useState(null);
  const [triggering, setTriggering] = useState(false);
  const [reporting, setReporting] = useState(false);

  // AI Brief Report State
  const [showAiReport, setShowAiReport] = useState(false);
  const [aiReportData, setAiReportData] = useState(null);
  const [aiReportLoading, setAiReportLoading] = useState(false);

  const refresh = useCallback(() => {
    getIncident(incidentId)
      .then(setIncident)
      .catch(() => {
        setIncident({
          incident_id: incidentId,
          type: "SUPPLIER_DELAY",
          severity: "CRITICAL",
          affected_component: "CMP-004",
          status: "WAITING_APPROVAL",
          title: `Active Disruption Incident — ${incidentId}`,
          description: "Operational supply chain disruption under autonomous AI agent investigation.",
          supplier_id: "SUP-001",
          created_at: new Date().toISOString()
        });
      });
    getAgentState(incidentId).then((r) => setAgentState(r?.state || "WAITING_APPROVAL")).catch(() => setAgentState("WAITING_APPROVAL"));
    getIncidentActivity(incidentId).then(setAuditLogs).catch(() => setAuditLogs([]));
    getAgentPlan(incidentId).then(setPlan).catch(() => setPlan(null));
  }, [incidentId]);

  useEffect(() => {
    refresh();
    const interval = setInterval(() => {
      if (agentState !== "RESOLVED") refresh();
    }, 2000);
    return () => clearInterval(interval);
  }, [refresh, agentState]);

  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerError(null);
    try {
      await triggerAgent(incidentId);
      refresh();
    } catch (err) {
      setTriggerError(err.message || "Failed to trigger agent.");
    } finally {
      setTriggering(false);
    }
  };

  const handleReport = async () => {
    setReporting(true);
    try {
      await downloadOperatorReport({ incidentId });
    } catch (err) {
      setTriggerError(err.message || "Failed to generate report.");
    } finally {
      setReporting(false);
    }
  };

  const handleToggleAiReport = async () => {
    if (!showAiReport && !aiReportData) {
      setAiReportLoading(true);
      try {
        const data = await getIncidentReport(incidentId);
        setAiReportData(data);
      } catch (err) {
        console.error("Failed to load incident report:", err);
      } finally {
        setAiReportLoading(false);
      }
    }
    setShowAiReport(!showAiReport);
  };

  if (!incident) {
    return (
      <div className="loading-shell">
        <span className="loading-orb" />
        <span>Loading incident…</span>
      </div>
    );
  }

  const currentStepIndex = FLOW_ORDER.indexOf(agentState);

  return (
    <div>
      <div className="panel elevated-panel">
        <div className="command-header">
          <div>
            <h2>{incident.affected_po || incident.incident_id} — {incident.type.replaceAll("_", " ")}</h2>
            <div className="command-meta">
              <SeverityBadge severity={incident.severity} />
              <StatusBadge status={agentState || incident.status} />
              <span className="command-id">{incident.incident_id}</span>
            </div>
          </div>
          <div className="command-actions">
            <button
              className="btn-ghost"
              disabled={aiReportLoading}
              onClick={handleToggleAiReport}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              {aiReportLoading ? "Analyzing…" : (showAiReport ? "Hide AI Brief" : "👁 AI Incident Brief")}
            </button>
            <button className="btn-ghost" disabled={reporting} onClick={handleReport}>
              {reporting ? "Preparing…" : "↓ Download PDF"}
            </button>
            <button className="btn-primary" disabled={triggering} onClick={handleTrigger}>
              {triggering ? "Triggering…" : "▶ Trigger Agent"}
            </button>
          </div>
        </div>

        <div className="flow-strip">
          {FLOW_STEPS.map((step, i) => (
            <span key={step.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className={`flow-step${i <= currentStepIndex ? " active" : ""}`}>{step.label}</span>
              {i < FLOW_STEPS.length - 1 && <span className="flow-sep">→</span>}
            </span>
          ))}
        </div>

        {triggerError && <div className="error-banner">{triggerError}</div>}
      </div>

      {/* AI Incident Executive Brief Panel */}
      {showAiReport && aiReportData && (
        <div className="panel elevated-panel" style={{ marginTop: 16, borderColor: "rgba(49, 87, 213, 0.4)", background: "rgba(49, 87, 213, 0.03)", padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, borderBottom: "1px solid var(--border-subtle)", paddingBottom: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="badge badge-primary">AI EXECUTIVE BRIEF</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                Comprehensive Operations Analysis — {incident.incident_id}
              </span>
            </div>
            <button className="btn-ghost" style={{ fontSize: 12 }} onClick={handleReport} disabled={reporting}>
              {reporting ? "Downloading…" : "↓ Download Formatted PDF"}
            </button>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--primary)", textTransform: "uppercase", marginBottom: 4 }}>
                Executive Summary
              </div>
              <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: "var(--text-secondary)" }}>
                {aiReportData.narrative?.executive_summary}
              </p>
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--primary)", textTransform: "uppercase", marginBottom: 4 }}>
                Supply Chain Impact & Stockout Risk
              </div>
              <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: "var(--text-secondary)" }}>
                {aiReportData.narrative?.impact_assessment}
              </p>
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--primary)", textTransform: "uppercase", marginBottom: 4 }}>
                Decision Rationale & Governance
              </div>
              <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: "var(--text-secondary)" }}>
                {aiReportData.narrative?.recovery_strategy}
              </p>
            </div>

            {aiReportData.narrative?.action_items && aiReportData.narrative.action_items.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--primary)", textTransform: "uppercase", marginBottom: 4 }}>
                  Actionable Directives
                </div>
                <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                  {aiReportData.narrative.action_items.map((act, idx) => (
                    <li key={idx} style={{ marginBottom: 2 }}>{act}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      <InfoCards incident={incident} plan={plan} />

      <div className="panel elevated-panel" style={{ marginTop: 16 }}>
        <h3>Agent Activity</h3>
        {auditLogs.length === 0 ? (
          <p className="empty-state">No activity yet — trigger the agent to begin investigating.</p>
        ) : (
          auditLogs.map((log, i) => (
            <div key={i} className="audit-line">
              <span className="audit-time">{new Date(log.timestamp).toLocaleTimeString()}</span>{" "}
              ✓ {log.action}
              {log.decision && <span className="audit-decision"> — {log.decision}: {log.reason}</span>}
            </div>
          ))
        )}
      </div>

      {plan && <RecoveryPlanPanel plan={plan} incident={incident} />}

      {agentState === "WAITING_APPROVAL" && plan && (
        <ApprovalModal plan={plan} incidentId={incidentId} onDecided={refresh} />
      )}
    </div>
  );
}