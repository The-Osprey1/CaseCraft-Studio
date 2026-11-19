// Desktop (pywebview) integration. The desktop launcher opens the UI as
//   http://127.0.0.1:<port>/?token=<per-launch token>
// so a token in the URL means "running inside CaseCraft Studio.exe". Everything here degrades to
// browser behaviour (downloads, <input type=file>) when that is not the case.

const params = new URLSearchParams(window.location.search);
export const TOKEN = params.get("token") || null;
export const IS_DESKTOP = Boolean(TOKEN);

let readyPromise = null;

/** Resolves true once window.pywebview.api is usable, false in a plain browser. */
export function desktopReady() {
  if (readyPromise) return readyPromise;
  readyPromise = new Promise((resolve) => {
    if (!IS_DESKTOP) return resolve(false);
    if (window.pywebview?.api?.app_info) return resolve(true);
    const done = () => resolve(Boolean(window.pywebview?.api));
    window.addEventListener("pywebviewready", done, { once: true });
    setTimeout(done, 8000);
  });
  return readyPromise;
}

/**
 * Call a DesktopBridge method. Never throws: always resolves to {ok, ...}; a closed dialog is
 * {ok: false, cancelled: true}.
 */
export async function call(name, ...args) {
  if (!(await desktopReady())) return { ok: false, error: "Only available in the desktop app" };
  const fn = window.pywebview?.api?.[name];
  if (typeof fn !== "function") return { ok: false, error: `Desktop feature '${name}' is unavailable` };
  try {
    const res = await fn(...args);
    return res && typeof res === "object" ? res : { ok: false, error: "No response from the app" };
  } catch (err) {
    return { ok: false, error: err?.message || String(err) };
  }
}

/** Yes/No question: a native Windows dialog in the desktop app, window.confirm in a browser. */
export async function confirmAction(message) {
  if (!IS_DESKTOP) return window.confirm(message);
  const r = await call("confirm", message);
  return r.ok ? Boolean(r.yes) : window.confirm(message);
}

/** Save text through the native Save dialog (desktop) or a browser download. */
export async function saveTextFile(suggestedName, text, mime, downloadBlob) {
  if (!IS_DESKTOP) {
    downloadBlob(new Blob([text], { type: mime }), suggestedName);
    return { ok: true };
  }
  const target = await call("save_file", suggestedName);
  if (!target.ok) return target;
  return call("write_text", target.path, text);
}

export async function copyDiagnostics() {
  const r = await call("diagnostics");
  if (!r.ok) return r;
  try {
    await navigator.clipboard.writeText(r.text);
    return { ok: true };
  } catch {
    return { ok: false, error: "Could not access the clipboard" };
  }
}
