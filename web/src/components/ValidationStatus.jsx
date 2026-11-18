import React, { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, ShieldQuestion, XCircle } from "lucide-react";

// Compact design-validation indicator: one state, concrete findings on click. No scores.
export function validationState({ status, error, invalid, findings }) {
  const list = findings || [];
  if (status === "loading" || status === "idle")
    return { tone: "slate", icon: Loader2, spin: true, label: "Checking design…", items: [] };
  if (status === "error") {
    const items = (error || "").split("; ").filter(Boolean).map((m) => ({ level: "error", message: m }));
    return {
      tone: "rose",
      icon: XCircle,
      label: invalid ? "Invalid design — export blocked" : "CAD error — export blocked",
      items,
    };
  }
  const errors = list.filter((f) => f.level === "error");
  const warnings = list.filter((f) => f.level === "warning");
  const infos = list.filter((f) => f.level === "info");
  const items = [...errors, ...warnings, ...infos];
  if (errors.length) return { tone: "rose", icon: XCircle, label: "Invalid design — export blocked", items };
  if (warnings.length)
    return { tone: "amber", icon: AlertTriangle, label: `Warning — review recommended (${warnings.length})`, items };
  if (infos.some((f) => f.source === "verification"))
    return { tone: "sky", icon: ShieldQuestion, label: "Verification pending", items };
  return { tone: "emerald", icon: CheckCircle2, label: "Ready to export", items };
}

const TONES = {
  slate: "border-slate-700 bg-slate-800/80 text-slate-300",
  rose: "border-rose-500/50 bg-rose-500/15 text-rose-200",
  amber: "border-amber-500/50 bg-amber-500/15 text-amber-200",
  sky: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  emerald: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
};
const DOT = { error: "bg-rose-400", warning: "bg-amber-400", info: "bg-sky-400" };

export default function ValidationStatus({ state, align = "right" }) {
  const [open, setOpen] = useState(false);
  const Icon = state.icon;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!state.items.length}
        title={state.items.length ? "Show findings" : undefined}
        className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${TONES[state.tone]}`}
      >
        <Icon className={`h-3.5 w-3.5 ${state.spin ? "animate-spin" : ""}`} />
        {state.label}
      </button>
      {open && state.items.length > 0 && (
        <div
          className={`absolute top-full z-40 mt-1.5 w-96 max-w-[90vw] rounded-xl border border-slate-700 bg-slate-900/95 p-3 shadow-2xl backdrop-blur ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          <ul className="max-h-80 space-y-2 overflow-y-auto">
            {state.items.map((f, i) => (
              <li key={i} className="flex gap-2 text-[11px] leading-snug text-slate-200">
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${DOT[f.level] || DOT.info}`} />
                <span>{f.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
