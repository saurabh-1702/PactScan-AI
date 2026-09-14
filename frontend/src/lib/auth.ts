"use client";

/**
 * Token storage + client-side role/tenant decode (Phase 5).
 *
 * Decoding the JWT payload here is for UI gating ONLY (e.g. hiding the
 * approvals link from an end_user) — it is never trusted for anything
 * security-relevant. The backend re-verifies the signature on every request;
 * a user could edit this decoded value in devtools and it would change
 * nothing about what the API actually lets them do.
 */

const TOKEN_KEY = "pactscan_token";

export interface DecodedToken {
  sub: string;
  tenant_id: string;
  role: "end_user" | "reviewer" | "admin";
  exp: number;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* private browsing / storage blocked — auth just won't persist */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function decodeToken(token: string): DecodedToken | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function getCurrentUser(): DecodedToken | null {
  const token = getToken();
  if (!token) return null;
  const decoded = decodeToken(token);
  if (!decoded) return null;
  if (decoded.exp * 1000 < Date.now()) {
    clearToken();
    return null;
  }
  return decoded;
}
