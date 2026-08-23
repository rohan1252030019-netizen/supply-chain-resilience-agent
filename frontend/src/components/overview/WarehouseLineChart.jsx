import { useRef, useState, useEffect } from "react";

const RANGE_DATA = {
  "7D": {
    xLabels: ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"],
    warehouseLoadPath: "M 50,150 Q 120,60 190,110 T 330,130 T 470,80",
    productDeliveriesPath: "M 50,160 Q 120,130 190,145 T 330,100 T 470,120",
    rawMaterialPath: "M 50,140 Q 120,110 190,125 T 330,80 T 470,60",
  },
  "30D": {
    xLabels: ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"],
    warehouseLoadPath: "M 50,164 Q 75,100 97,105 T 144,115 T 191,135 T 238,148 T 285,160 T 332,168 T 379,155 T 426,148 T 473,135 T 520,105",
    productDeliveriesPath: "M 50,164 Q 75,160 97,150 T 144,160 T 191,150 T 238,140 T 285,130 T 332,145 T 379,135 T 426,130 T 473,115 T 520,135",
    rawMaterialPath: "M 50,164 Q 75,135 97,140 T 144,155 T 191,145 T 238,130 T 285,115 T 332,140 T 379,150 T 426,155 T 473,110 T 520,100",
  },
  "90D": {
    xLabels: ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W12"],
    warehouseLoadPath: "M 50,120 Q 100,70 150,90 T 250,140 T 350,110 T 450,75 T 520,95",
    productDeliveriesPath: "M 50,145 Q 100,120 150,130 T 250,90 T 350,130 T 450,100 T 520,115",
    rawMaterialPath: "M 50,135 Q 100,90 150,110 T 250,70 T 350,95 T 450,55 T 520,70",
  },
  "YTD": {
    xLabels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"],
    warehouseLoadPath: "M 50,140 Q 110,85 170,100 T 290,135 T 410,95 T 520,70",
    productDeliveriesPath: "M 50,155 Q 110,135 170,120 T 290,80 T 410,110 T 520,125",
    rawMaterialPath: "M 50,130 Q 110,100 170,115 T 290,65 T 410,85 T 520,50",
  },
};

export default function WarehouseLineChart() {
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [showOptionsMenu, setShowOptionsMenu] = useState(false);
  const [activeRange, setActiveRange] = useState("30D");
  const [visibleSeries, setVisibleSeries] = useState({
    rawMaterial: true,
    productDeliveries: true,
    warehouseLoad: true,
  });

  const filterRef = useRef(null);
  const optionsRef = useRef(null);

  // Click outside to close dropdowns
  useEffect(() => {
    const handler = (e) => {
      if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilterMenu(false);
      if (optionsRef.current && !optionsRef.current.contains(e.target)) setShowOptionsMenu(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const currentConfig = RANGE_DATA[activeRange] || RANGE_DATA["30D"];
  const yLabels = [200, 150, 100, 50, 0];

  const handleExportCsv = () => {
    const csvContent =
      "data:text/csv;charset=utf-8,Period,Raw Material,Product Deliveries,Warehouse Load\n" +
      currentConfig.xLabels.map((l, i) => `${l},${30 + i * 5},${20 + i * 8},${60 + i * 3}`).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `warehouse-workload-${activeRange.toLowerCase()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const toggleSeries = (key) => {
    setVisibleSeries((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="dashboard-card" style={{ position: "relative" }}>
      {/* Header */}
      <div className="card-header-row">
        <div>
          <span className="card-header-title">Warehouse workload</span>
          <span style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700, marginLeft: 8, background: "rgba(37,99,235,0.08)", padding: "2px 8px", borderRadius: 12 }}>
            {activeRange}
          </span>
        </div>
        <div className="card-header-actions" style={{ position: "relative", display: "flex", gap: 6 }}>
          
          {/* ── Funnel Filter Button & Popover ── */}
          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              className="action-icon-btn"
              title="Filter Chart Data"
              onClick={() => { setShowFilterMenu((v) => !v); setShowOptionsMenu(false); }}
              style={{
                background: showFilterMenu ? "var(--bg-panel-raised)" : "#FFFFFF",
                borderColor: showFilterMenu ? "var(--primary)" : "var(--border-subtle)",
                color: showFilterMenu ? "var(--primary)" : "var(--text-secondary)",
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
              </svg>
            </button>

            {showFilterMenu && (
              <div style={{
                position: "absolute", top: "calc(100% + 8px)", right: 0,
                width: 220, background: "#FFFFFF", borderRadius: 14,
                border: "1px solid var(--border-subtle)", boxShadow: "0 14px 40px rgba(15,23,42,0.15)",
                zIndex: 1000, padding: 14, fontSize: 12,
              }}>
                <div style={{ fontWeight: 700, marginBottom: 8, color: "var(--text-muted)", textTransform: "uppercase", fontSize: 10, letterSpacing: "0.06em" }}>
                  Time Horizon
                </div>
                <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
                  {["7D", "30D", "90D", "YTD"].map((range) => (
                    <button
                      key={range}
                      onClick={() => { setActiveRange(range); setShowFilterMenu(false); }}
                      style={{
                        flex: 1, padding: "6px 0", borderRadius: 8, border: "1px solid var(--border-subtle)",
                        background: activeRange === range ? "var(--primary)" : "#F8FAFC",
                        color: activeRange === range ? "#FFFFFF" : "var(--text-primary)",
                        fontWeight: 700, fontSize: 11, cursor: "pointer", transition: "all 0.15s ease",
                      }}
                    >
                      {range}
                    </button>
                  ))}
                </div>

                <div style={{ fontWeight: 700, marginBottom: 8, color: "var(--text-muted)", textTransform: "uppercase", fontSize: 10, letterSpacing: "0.06em" }}>
                  Toggle Data Series
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={visibleSeries.rawMaterial} onChange={() => toggleSeries("rawMaterial")} />
                    <span style={{ color: "#EF4444", fontWeight: 600 }}>Raw Material</span>
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={visibleSeries.productDeliveries} onChange={() => toggleSeries("productDeliveries")} />
                    <span style={{ color: "#10B981", fontWeight: 600 }}>Product Deliveries</span>
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <input type="checkbox" checked={visibleSeries.warehouseLoad} onChange={() => toggleSeries("warehouseLoad")} />
                    <span style={{ color: "#F59E0B", fontWeight: 600 }}>Warehouse Load</span>
                  </label>
                </div>
              </div>
            )}
          </div>

          {/* ── 3-Dot Options Button & Popover ── */}
          <div ref={optionsRef} style={{ position: "relative" }}>
            <button
              className="action-icon-btn"
              title="More Options"
              onClick={() => { setShowOptionsMenu((v) => !v); setShowFilterMenu(false); }}
              style={{
                background: showOptionsMenu ? "var(--bg-panel-raised)" : "#FFFFFF",
                borderColor: showOptionsMenu ? "var(--primary)" : "var(--border-subtle)",
                color: showOptionsMenu ? "var(--primary)" : "var(--text-secondary)",
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="5" cy="12" r="2"/>
                <circle cx="12" cy="12" r="2"/>
                <circle cx="19" cy="12" r="2"/>
              </svg>
            </button>

            {showOptionsMenu && (
              <div style={{
                position: "absolute", top: "calc(100% + 8px)", right: 0,
                width: 180, background: "#FFFFFF", borderRadius: 14,
                border: "1px solid var(--border-subtle)", boxShadow: "0 14px 40px rgba(15,23,42,0.15)",
                zIndex: 1000, padding: 6, fontSize: 12,
              }}>
                <button
                  onClick={() => { handleExportCsv(); setShowOptionsMenu(false); }}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "8px 10px", borderRadius: 8, border: "none", background: "none",
                    cursor: "pointer", fontSize: 12, color: "var(--text-primary)", textAlign: "left",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#F1F5F9")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
                >
                  <span>📥</span> Export CSV Data
                </button>

                <button
                  onClick={() => {
                    setVisibleSeries({ rawMaterial: true, productDeliveries: true, warehouseLoad: true });
                    setActiveRange("30D");
                    setShowOptionsMenu(false);
                  }}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "8px 10px", borderRadius: 8, border: "none", background: "none",
                    cursor: "pointer", fontSize: 12, color: "var(--text-primary)", textAlign: "left",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#F1F5F9")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
                >
                  <span>🔄</span> Reset Chart Filters
                </button>
              </div>
            )}
          </div>

        </div>
      </div>

      {/* SVG Multi-Line Chart */}
      <div className="line-chart-container">
        <svg viewBox="0 0 540 200" width="100%" height="100%" preserveAspectRatio="none">
          {/* Y-Axis Labels */}
          {yLabels.map((val, idx) => {
            const y = 20 + idx * 36;
            return (
              <text
                key={val}
                x="20"
                y={y + 4}
                fill="#94A3B8"
                fontSize="11"
                fontFamily="Inter, sans-serif"
                fontWeight="500"
                textAnchor="end"
              >
                {val}
              </text>
            );
          })}

          {/* Vertical dashed grid lines & Dynamic X-axis labels */}
          {currentConfig.xLabels.map((lbl, idx) => {
            const step = (530 - 50) / Math.max(1, currentConfig.xLabels.length - 1);
            const x = 50 + idx * step;
            return (
              <g key={`${lbl}-${idx}`}>
                <line
                  x1={x}
                  y1={15}
                  x2={x}
                  y2={164}
                  stroke="#E2E8F0"
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />
                <text
                  x={x}
                  y={184}
                  fill="#94A3B8"
                  fontSize="11"
                  fontFamily="Inter, sans-serif"
                  fontWeight="500"
                  textAnchor="middle"
                >
                  {lbl}
                </text>
              </g>
            );
          })}

          {/* Bottom baseline */}
          <line x1="45" y1="164" x2="530" y2="164" stroke="#E2E8F0" strokeWidth="1" />

          {/* Line 1: Yellow - "Warehouse load" */}
          {visibleSeries.warehouseLoad && (
            <path
              d={currentConfig.warehouseLoadPath}
              fill="none"
              stroke="#F59E0B"
              strokeWidth="2.4"
              strokeLinecap="round"
              style={{ transition: "d 0.3s ease" }}
            />
          )}

          {/* Line 2: Green - "Product deliveries" */}
          {visibleSeries.productDeliveries && (
            <path
              d={currentConfig.productDeliveriesPath}
              fill="none"
              stroke="#10B981"
              strokeWidth="2.4"
              strokeLinecap="round"
              style={{ transition: "d 0.3s ease" }}
            />
          )}

          {/* Line 3: Red - "Raw material" */}
          {visibleSeries.rawMaterial && (
            <path
              d={currentConfig.rawMaterialPath}
              fill="none"
              stroke="#EF4444"
              strokeWidth="2.4"
              strokeLinecap="round"
              style={{ transition: "d 0.3s ease" }}
            />
          )}
        </svg>
      </div>

      {/* Legend */}
      <div className="line-chart-legend">
        <div
          className="legend-item"
          onClick={() => toggleSeries("rawMaterial")}
          style={{ cursor: "pointer", opacity: visibleSeries.rawMaterial ? 1 : 0.4 }}
          title="Click to toggle Raw Material line"
        >
          <span className="legend-dot red" />
          <span style={{ fontWeight: visibleSeries.rawMaterial ? 600 : 400 }}>Raw material</span>
        </div>

        <div
          className="legend-item"
          onClick={() => toggleSeries("productDeliveries")}
          style={{ cursor: "pointer", opacity: visibleSeries.productDeliveries ? 1 : 0.4 }}
          title="Click to toggle Product Deliveries line"
        >
          <span className="legend-dot green" />
          <span style={{ fontWeight: visibleSeries.productDeliveries ? 600 : 400 }}>Product deliveries</span>
        </div>

        <div
          className="legend-item"
          onClick={() => toggleSeries("warehouseLoad")}
          style={{ cursor: "pointer", opacity: visibleSeries.warehouseLoad ? 1 : 0.4 }}
          title="Click to toggle Warehouse Load line"
        >
          <span className="legend-dot yellow" />
          <span style={{ fontWeight: visibleSeries.warehouseLoad ? 600 : 400 }}>Warehouse load</span>
        </div>
      </div>
    </div>
  );
}
