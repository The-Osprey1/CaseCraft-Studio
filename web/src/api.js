// Small fetch helpers shared by the preview and export hooks.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
    // 422 = the design itself is invalid (same rule set as the CLI); anything else is a server/CAD error
    this.invalid = status === 422;
  }
}

export async function postJson(url, body, { signal } = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : `Server error (${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return res;
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
  URL.revokeObjectURL(url);
}

// Stable identity of "what is being designed": the full config plus the printer profile.
// Previews and exports are only considered current when their key equals this.
export function designKey(config, printerId) {
  return config ? JSON.stringify([config, printerId]) : null;
}
