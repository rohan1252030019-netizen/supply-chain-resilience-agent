import { getApiBaseUrl } from "./client.js";

export async function fetchReportPreview({ incidentId, startDate, endDate, includeDiagnostics = false, orderId, supplierId } = {}) {
  const BASE_URL = getApiBaseUrl();
  const params = new URLSearchParams();
  if (incidentId) params.set("incident_id", incidentId);
  if (orderId) params.set("order_id", orderId);
  if (supplierId) params.set("supplier_id", supplierId);
  if (startDate) params.set("start_date", new Date(`${startDate}T00:00:00Z`).toISOString());
  if (endDate) params.set("end_date", new Date(`${endDate}T23:59:59Z`).toISOString());
  if (includeDiagnostics) params.set("include_diagnostics", "true");

  const token = localStorage.getItem("scda_auth_token");
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
  };

  const response = await fetch(`${BASE_URL}/audit/report/preview?${params}`, { headers });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Report preview failed: ${response.status}`);
  }
  return response.json();
}

export async function downloadOperatorReport({ incidentId, startDate, endDate, includeDiagnostics = false, orderId, supplierId } = {}) {
  const BASE_URL = getApiBaseUrl();
  const params = new URLSearchParams();
  if (incidentId) params.set("incident_id", incidentId);
  if (orderId) params.set("order_id", orderId);
  if (supplierId) params.set("supplier_id", supplierId);
  if (startDate) params.set("start_date", new Date(`${startDate}T00:00:00Z`).toISOString());
  if (endDate) params.set("end_date", new Date(`${endDate}T23:59:59Z`).toISOString());
  if (includeDiagnostics) params.set("include_diagnostics", "true");

  const token = localStorage.getItem("scda_auth_token");
  const headers = {
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
  };

  const response = await fetch(`${BASE_URL}/audit/report/operator.pdf?${params}`, { headers });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Report generation failed: ${response.status}`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = response.headers.get("content-disposition")?.match(/filename="?([^";]+)"?/)?.[1] || "supply-chain-report.pdf";
  link.click();
  URL.revokeObjectURL(url);
}
