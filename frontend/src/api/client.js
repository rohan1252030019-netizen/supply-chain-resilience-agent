/**
 * src/api/client.js
 * Owner: Developer 4 (Frontend)
 *
 * Single fetch wrapper every other file in src/api/ uses. Keeps base URL,
 * error handling, and JSON parsing in one place.
 * Automatically injects the JWT token from localStorage and fires an
 * event if a 401 is encountered.
 */

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== "undefined" &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
    ? (window.location.hostname.includes("quick-pasteur")
        ? window.location.origin
        : "https://scda-fastapi-backend.onrender.com")
    : "http://localhost:8000");

export async function apiRequest(path, options = {}) {
  const token = localStorage.getItem("scda_auth_token");
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  // Only trigger unauthorized event for protected API routes, not public auth or health endpoints
  if (
    res.status === 401 &&
    !path.startsWith("/auth/") &&
    !path.startsWith("/health")
  ) {
    localStorage.removeItem("scda_auth_token");
    localStorage.removeItem("scda_auth_user");
    window.dispatchEvent(new CustomEvent("scda_unauthorized"));
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${options.method || "GET"} ${path} failed: ${res.status} ${body}`);
  }

  if (res.status === 204) return null;
  return res.json();
}
