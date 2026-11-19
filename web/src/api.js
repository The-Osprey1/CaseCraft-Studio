// Small fetch helpers shared by the preview and export hooks.
import { TOKEN } from "./desktop.js";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
    // 422 = the design itself is invalid (same rule set as the CLI); anything else is a server/CAD error
    this.invalid = status === 422;
  }
}

export function authHeaders(extra = {}) {
  return TOKEN ? { ...extra, "X-CaseCraft-Token": TOKEN } : extra;
}

/** fetch() with the desktop token, readable errors for HTTP failures and a dead server. */
export async function apiFetch(url, options = {}) {
  let res;
  try {
    res = await fetch(url, { ...options, headers: authHeaders(options.headers) });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(
      "The CAD engine is not responding. Wait a moment and try again; if it persists, restart CaseCraft Studio.",
      0
    );
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : `Server error (${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return res;
}

export async function postJson(url, body, { signal } = {}) {
  return apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export function filenameFrom(res, fallback) {
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="([^"]+)"/);
  return m ? m[1] : fallback;
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // revoke later: revoking synchronously can cancel the download in some engines
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

// Stable identity of "what is being designed": the full config plus the printer profile.
// Previews and exports are only considered current when their key equals this.
export function designKey(config, printerId) {
  return config ? JSON.stringify([config, printerId]) : null;
}
