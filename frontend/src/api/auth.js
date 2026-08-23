/**
 * src/api/auth.js
 *
 * Authentication API calls: login, register, logout, me, forgot/reset password.
 */

import { getApiBaseUrl } from "./client.js";

async function request(path, options = {}, token = null) {
  const BASE_URL = getApiBaseUrl();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { headers, ...options });

  // Auth endpoints — parse body even on error for detail messages
  const body = await res.json().catch(() => ({ detail: "Server error" }));

  if (!res.ok) {
    const err = new Error(body.detail || `HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

export const authApi = {
  /** Register a new account (user or supplier) */
  register: (payload) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Login with email + password */
  login: (email, password) =>
    request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  /** Logout (clears server cookie) */
  logout: (token) =>
    request("/auth/logout", { method: "POST" }, token),

  /** Fetch current user profile */
  me: (token) => request("/auth/me", {}, token),

  /** Request password reset */
  forgotPassword: (email) =>
    request("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  /** Apply new password with reset token */
  resetPassword: (token, new_password, confirm_password) =>
    request("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password, confirm_password }),
    }),
};
