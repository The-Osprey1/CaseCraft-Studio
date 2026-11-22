import React from "react";
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import PlatePreview from "./PlatePreview.jsx";

const FINISH = { through: "Through-cut", deboss: "Deboss", inlay: "Inlay" };

function status(data, error) {
  if (error) return { tone: "rose", icon: XCircle, title: "This design can't be built", detail: error };
  if (!data) return null;
  const islands = data.connectivity?.islands || 0;
  if (islands)
    return {
      tone: "rose",
      icon: XCircle,
      title: `${islands} ${islands === 1 ? "piece" : "pieces"} would fall out`,
      detail: (data.error || "").replace(/^Your through-cut \w+ pattern creates [^.]+\. /, ""),
    };
  if (data.error) return { tone: "rose", icon: XCircle, title: "This design can't be built", detail: data.error };
  if (data.type === "solid") return { tone: "emerald", icon: CheckCircle2, title: "Solid backplate" };
  if (!data.stats?.cuts) return { tone: "amber", icon: AlertTriangle, title: "Nothing to cut yet" };
  if (data.mode === "through" && (data.thin || data.connectivity?.thin_necks))
    return {
      tone: "amber",
      icon: AlertTriangle,
      title: "Some ligaments are thinner than one extrusion",
      detail: "Highlighted in amber. Increase the web or the border margin.",
    };
  if (data.warnings?.length) return { tone: "amber", icon: AlertTriangle, title: "Review recommended", detail: data.warnings[0] };
  if (data.mode === "through") return { tone: "emerald", icon: CheckCircle2, title: "Prints as one piece" };
  return { tone: "emerald", icon: CheckCircle2, title: data.mode === "inlay" ? "Two-colour inlay" : "Recessed engraving" };
}

const TONE = {
  rose: "text-rose-300",
  amber: "text-amber-300",
  emerald: "text-emerald-300",
};

function openLabel(mode, pct) {
  if (mode === "deboss") return `${pct}% of the back recessed`;
  if (mode === "inlay") return `${pct}% of the back in the inlay colour`;
  return `${pct}% open area`;
}

/**
 * Live back view of the case beside the pattern controls. Pinned to the top of the scrolling
 * panel so it stays in sight while sliders further down are dragged.
 */
export default function PatternPreviewCard({ request, colors, typeLabel }) {
  const { data, error, loading, current } = request;
  const st = status(data, error);
  const Icon = st?.icon;
  const pct = data?.stats?.open_area_pct ?? 0;
  return (
    <div className="sticky top-0 z-10 -mx-4 -mt-4 border-b border-slate-800 bg-slate-900/95 px-4 py-3 backdrop-blur">
      <div className="flex gap-4">
        <div className="relative shrink-0">
          <PlatePreview
            frame={data}
            cuts={data?.cuts}
            colors={colors}
            mode={data?.mode}
            showIssues
            issues={data}
            dim={Boolean(error) || (loading && !current && Boolean(data))}
            className="h-52 w-[100px]"
            label="Back of the case"
          />
          {loading && (
            <Loader2 className="absolute -right-1.5 -top-1.5 h-3.5 w-3.5 animate-spin text-cyan-400" aria-label="Updating" />
          )}
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <div className="text-sm font-semibold text-white">{typeLabel || "Backplate"}</div>
          {data?.type !== "solid" && data && (
            <div className="mt-0.5 text-xs text-slate-400">{FINISH[data.mode] || data.mode}</div>
          )}
          {data?.stats?.cuts > 0 && (
            <dl className="mt-2.5 space-y-0.5 text-xs text-slate-300">
              <div>
                <dt className="sr-only">Cut-outs</dt>
                <dd>{data.stats.cuts} cut-outs</dd>
              </div>
              <div>
                <dt className="sr-only">Coverage</dt>
                <dd>{openLabel(data.mode, pct)}</dd>
              </div>
            </dl>
          )}
          {st && (
            <div className={`mt-2.5 text-xs ${TONE[st.tone]}`} role="status">
              <div className="flex items-start gap-1.5 font-medium">
                <Icon className="mt-px h-3.5 w-3.5 shrink-0" />
                <span>{st.title}</span>
              </div>
              {st.detail && <p className="mt-1 text-[11px] leading-snug text-slate-400">{st.detail}</p>}
            </div>
          )}
          <p className="mt-2.5 text-[11px] text-slate-500">Seen from the back</p>
        </div>
      </div>
    </div>
  );
}
