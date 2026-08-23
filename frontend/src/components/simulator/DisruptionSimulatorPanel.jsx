import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { injectScenario } from "../../api/simulator.js";

const SCENARIOS = [
  {
    key: "SUPPLIER_DELAY",
    title: "Supplier Lead-Time Delay",
    icon: "⏱️",
    badge: "HIGH RISK",
    badgeColor: "#F59E0B",
    description: "Primary vendor reports 7-day logistics delay. Simulates safety stock runway evaluation and split PO backup routing.",
  },
  {
    key: "STALE_INVENTORY",
    title: "Stale Inventory Expiration",
    icon: "📦",
    badge: "CRITICAL",
    badgeColor: "#EF4444",
    description: "Component batch exceeds shelf-life limits. Triggers quality hold, stock write-off, and emergency replenishment PO.",
  },
  {
    key: "SUPPLIER_LIE",
    title: "Supplier Dispatch Misrepresentation",
    icon: "🚨",
    badge: "HIGH RISK",
    badgeColor: "#F59E0B",
    description: "GPS tracking mismatch vs vendor declared dispatch date. Flags supplier reliability penalty & initiates audit trail.",
  },
  {
    key: "QUALITY_FAILURE",
    title: "Batch Defect Quality Failure",
    icon: "🛡️",
    badge: "CRITICAL",
    badgeColor: "#EF4444",
    description: "Inbound lot fails AQL inspection. Initiates lot rejection, quarantine, and secondary supplier allocation.",
  },
  {
    key: "BUDGET_OVERRUN",
    title: "Autonomous Threshold Escalation",
    icon: "⚖️",
    badge: "APPROVAL REQ",
    badgeColor: "#2563EB",
    description: "Recovery plan cost exceeds ₹50,000 threshold. Routes incident to Executive Governance & Approvals dashboard.",
  },
];

export default function DisruptionSimulatorPanel() {
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [injecting, setInjecting] = useState(null);
  const [lastIncident, setLastIncident] = useState(null);

  const handleInject = async (scenarioKey) => {
    setInjecting(scenarioKey);
    setError(null);
    try {
      const incident = await injectScenario(scenarioKey);
      setLastIncident(incident);
      if (incident?.incident_id) {
        navigate(`/incidents/${incident.incident_id}`);
      }
    } catch (err) {
      setError(err.message || "Failed to inject scenario.");
    } finally {
      setInjecting(null);
    }
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
          Supply Chain Disruption Simulator
        </h1>
        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 14 }}>
          Inject real-time operational disruptions into the resilience engine to test AI agent investigation, multi-criteria recovery options, and executive governance.
        </p>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: 20 }}>
          {error}
        </div>
      )}

      {/* Grid of Scenario Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
        {SCENARIOS.map((s) => {
          const isCurrent = injecting === s.key;
          return (
            <div
              key={s.key}
              style={{
                background: "#FFFFFF",
                borderRadius: 18,
                border: "1px solid var(--border-subtle)",
                boxShadow: "0 8px 24px rgba(15, 23, 42, 0.05)",
                padding: "24px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                transition: "all 0.2s ease",
              }}
            >
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <div style={{ fontSize: 24 }}>{s.icon}</div>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "3px 10px",
                      borderRadius: 12,
                      background: `${s.badgeColor}15`,
                      color: s.badgeColor,
                      border: `1px solid ${s.badgeColor}30`,
                      letterSpacing: "0.05em",
                    }}
                  >
                    {s.badge}
                  </span>
                </div>

                <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>
                  {s.title}
                </h3>

                <p style={{ margin: 0, fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  {s.description}
                </p>
              </div>

              <div style={{ marginTop: 20 }}>
                <button
                  disabled={!!injecting}
                  onClick={() => handleInject(s.key)}
                  style={{
                    width: "100%",
                    background: isCurrent ? "var(--text-muted)" : "linear-gradient(135deg, #2563EB 0%, #00C6FF 100%)",
                    color: "#FFFFFF",
                    border: "none",
                    borderRadius: 10,
                    padding: "10px 16px",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: injecting ? "not-allowed" : "pointer",
                    boxShadow: "0 4px 12px rgba(37, 99, 235, 0.25)",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 8,
                    transition: "all 0.15s ease",
                  }}
                >
                  <span>⚡</span>
                  {isCurrent ? "Injecting Scenario…" : "Inject Disruption"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {lastIncident && (
        <div
          style={{
            marginTop: 24,
            padding: "16px 20px",
            background: "rgba(16, 185, 129, 0.08)",
            border: "1px solid rgba(16, 185, 129, 0.3)",
            borderRadius: 14,
            fontSize: 13,
            color: "#065F46",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            ✓ Disruption <strong>{lastIncident.incident_id}</strong> injected successfully. AI Agent investigation initiated.
          </div>
          <Link
            to={`/incidents/${lastIncident.incident_id}`}
            style={{ fontWeight: 700, color: "var(--primary)", textDecoration: "none" }}
          >
            Open Command Center →
          </Link>
        </div>
      )}
    </div>
  );
}