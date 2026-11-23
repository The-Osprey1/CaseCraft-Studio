import React from "react";
import { FileCode2, Grid3X3, Layers, Loader2, RefreshCw } from "lucide-react";

const MODES = [
  { id: "assembly", label: "3D assembly", icon: Layers },
  { id: "bed", label: "Print bed", icon: Grid3X3 },
  { id: "svg", label: "Laser SVG", icon: FileCode2 },
];

const PRESETS = [
  { id: "front", label: "Front", hint: "Screen side" },
  { id: "back", label: "Back", hint: "Backplate and pattern" },
  { id: "side", label: "Side", hint: "Buttons and lip profile" },
  { id: "iso", label: "3/4", hint: "Three-quarter view" },
];

const chip = "rounded-lg border bg-slate-900/85 px-2.5 py-1.5 text-xs shadow backdrop-blur-md";

/**
 * Viewport HUD: what is shown (assembly / print bed / laser SVG), where the camera looks,
 * the explode and phone-ghost aids, and the rebuild state of the 3D model.
 */
export default function ViewportToolbar({
  preview,
  viewMode,
  onViewMode,
  onView,
  explode,
  onExplode,
  showPhoneGhost,
  onTogglePhoneGhost,
  loading,
  dirty,
  canRebuild,
  onRebuild,
}) {
  return (
    <div className="pointer-events-none absolute left-3 right-3 top-3 z-20 flex flex-wrap items-start justify-between gap-2">
      <div className="pointer-events-auto flex flex-wrap items-center gap-1.5">
        {viewMode === "bed" && (
          <span
            className={`${chip} font-medium ${
              preview?.bed?.fits === false ? "border-rose-500/60 text-rose-300" : "border-cyan-500/40 text-cyan-300"
            }`}
          >
            {preview?.printer?.name || "Build plate"}, {preview?.bed?.x ?? 256} × {preview?.bed?.y ?? 256} mm
            {preview?.bed?.fits === false ? ": parts do not fit" : ""}
          </span>
        )}
        {preview?.summary && (
          <span className={`${chip} border-slate-800 text-slate-300`}>
            Case {preview.summary.outer_width} × {preview.summary.outer_length} × {preview.summary.total_height} mm
          </span>
        )}
        {(loading || dirty) && (
          <span
            className={`${chip} flex items-center gap-1.5 font-medium ${
              loading ? "border-cyan-500/40 text-cyan-300" : "border-amber-500/40 text-amber-300"
            }`}
            role="status"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {loading ? "Rebuilding 3D model…" : "Showing the last valid model"}
          </span>
        )}
      </div>

      <div className="pointer-events-auto flex flex-wrap items-center gap-2 rounded-xl border border-slate-800/90 bg-slate-900/85 p-1.5 shadow-xl backdrop-blur-md">
        <div className="flex items-center gap-0.5 rounded-lg bg-slate-950/80 p-0.5 text-xs" role="tablist" aria-label="View">
          {MODES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={viewMode === id}
              onClick={() => onViewMode(id)}
              className={`flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1 font-medium transition ${
                viewMode === id
                  ? "border border-cyan-500/30 bg-cyan-500/20 text-cyan-300"
                  : "border border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        {viewMode === "assembly" && (
          <>
            <div className="flex items-center gap-0.5" aria-label="Camera">
              {PRESETS.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  title={v.hint}
                  onClick={() => onView(v.id)}
                  className="rounded-md px-2 py-1 text-[11px] font-medium text-slate-300 transition hover:bg-slate-800 hover:text-white"
                >
                  {v.label}
                </button>
              ))}
            </div>
            <div className="h-4 w-px bg-slate-800" />
            <label className="flex items-center gap-2 px-1">
              <span className="text-[11px] font-medium text-slate-400">Explode</span>
              <input
                aria-label="Exploded view"
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={explode}
                onChange={(e) => onExplode(parseFloat(e.target.value))}
                className="h-1.5 w-20 cursor-pointer accent-cyan-400"
              />
            </label>
            <button
              type="button"
              aria-pressed={showPhoneGhost}
              onClick={onTogglePhoneGhost}
              className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
                showPhoneGhost
                  ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-300"
                  : "border-slate-700 text-slate-400 hover:text-slate-200"
              }`}
            >
              Phone
            </button>
          </>
        )}

        <button
          type="button"
          disabled={!canRebuild || loading}
          onClick={onRebuild}
          title="Rebuild the 3D model now"
          className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-700/80 bg-slate-800/80 px-2.5 py-1 text-[11px] font-medium text-slate-200 transition hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" /> : <RefreshCw className="h-3.5 w-3.5 text-cyan-400" />}
          Rebuild
        </button>
      </div>
    </div>
  );
}
