import React, { useEffect, useMemo, useState } from "react";
import { ChevronLeft, Search, X } from "lucide-react";
import DeviceBadge from "./DeviceBadge.jsx";
import { cleanDeviceName } from "../constants.jsx";

export const MY_DEVICES = "My devices";
export const OTHER_BRAND = "Other";

export function deviceBrand(preset, userIds = []) {
  if (userIds.includes(preset.id)) return MY_DEVICES;
  return (preset.brand || "").trim() || OTHER_BRAND;
}

const byNewest = (a, b) =>
  (b.year || 0) - (a.year || 0) ||
  cleanDeviceName(a.name).localeCompare(cleanDeviceName(b.name), undefined, { numeric: true });

/** [[brand, models newest-first], ...]: My devices first, then makers by model count, Other last. */
export function groupByBrand(presets, userIds = []) {
  const groups = new Map();
  for (const p of presets) {
    const b = deviceBrand(p, userIds);
    if (!groups.has(b)) groups.set(b, []);
    groups.get(b).push(p);
  }
  for (const list of groups.values()) list.sort(byNewest);
  const rank = (b) => (b === MY_DEVICES ? 0 : b === OTHER_BRAND ? 2 : 1);
  return [...groups.entries()].sort(
    ([a, la], [b, lb]) => rank(a) - rank(b) || lb.length - la.length || a.localeCompare(b)
  );
}

function ModelCard({ preset, active, isUser, showBrand, onSelect }) {
  const b = preset.body;
  return (
    <button
      type="button"
      onClick={() => onSelect(preset.id)}
      aria-pressed={active}
      className={`group flex flex-col gap-1.5 rounded-xl border p-3 text-left transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
        active
          ? "border-cyan-400 bg-cyan-500/10 ring-1 ring-cyan-400/25"
          : "border-slate-800 bg-slate-900/70 hover:border-slate-700 hover:bg-slate-800/40"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {showBrand && <div className="text-[10px] uppercase tracking-wide text-slate-500">{deviceBrand(preset, isUser ? [preset.id] : [])}</div>}
          <div className="text-xs font-semibold leading-snug text-white group-hover:text-cyan-200">
            {cleanDeviceName(preset.name)}
          </div>
        </div>
        {active && (
          <span className="shrink-0 rounded-full border border-cyan-400/30 bg-cyan-400/20 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-300">
            Active
          </span>
        )}
      </div>
      <div className="font-mono text-[10.5px] text-slate-400">
        {b.length} × {b.width} × {b.thickness} mm
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {preset.year > 0 && <span className="text-[10px] text-slate-500">{preset.year}</span>}
        <DeviceBadge verification={preset.verification} />
        {preset.camera?.ring === false && (
          <span
            title="The camera island reaches the edge of the backplate (or is a full-width plateau): the case gets an open camera cut-out instead of a press-fit ring"
            className="rounded-full border border-slate-700 bg-slate-800/70 px-1.5 py-0.5 text-[10px] text-slate-300"
          >
            Open camera cut-out
          </span>
        )}
        {isUser && (
          <span className="rounded-full border border-violet-400/30 bg-violet-400/10 px-1.5 py-0.5 text-[10px] font-medium text-violet-300">
            My device
          </span>
        )}
      </div>
    </button>
  );
}

/**
 * Wizard step 1: pick the maker first, then the model. A search box finds a model across every
 * maker. The maker of the active device is open initially.
 */
export default function DevicePicker({ presets, userPresetIds = [], activeId, activeBrand, onSelect }) {
  const groups = useMemo(() => groupByBrand(presets, userPresetIds), [presets, userPresetIds]);
  const brands = groups.map(([b]) => b);
  const [brand, setBrand] = useState(null);
  const [query, setQuery] = useState("");

  // open the active device's maker until the user picks one
  useEffect(() => {
    if (brand === null && brands.length) setBrand(brands.includes(activeBrand) ? activeBrand : brands[0]);
  }, [brand, brands, activeBrand]);

  const q = query.trim().toLowerCase();
  const matches = q
    ? presets
        .filter((p) =>
          `${cleanDeviceName(p.name)} ${deviceBrand(p, userPresetIds)} ${p.year || ""}`.toLowerCase().includes(q)
        )
        .sort(byNewest)
    : null;
  const models = matches || groups.find(([b]) => b === brand)?.[1] || [];

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search models"
          aria-label="Search phone models"
          className="w-full rounded-lg border border-slate-800 bg-slate-950 py-1.5 pl-8 pr-8 text-xs text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-500"
        />
        {query && (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => setQuery("")}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-200"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      {!matches && (
        <div role="tablist" aria-label="Phone maker" className="grid grid-cols-2 gap-2 xl:grid-cols-3">
          {groups.map(([b, list]) => {
            const selected = b === brand;
            const hasActive = list.some((p) => p.id === activeId);
            return (
              <button
                key={b}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setBrand(b)}
                className={`flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
                  selected
                    ? "border-cyan-400 bg-cyan-500/10 text-white"
                    : "border-slate-800 bg-slate-900/70 text-slate-300 hover:border-slate-700 hover:text-white"
                }`}
              >
                <span
                  aria-hidden
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold ${
                    selected ? "bg-cyan-400 text-slate-950" : "bg-slate-800 text-slate-300"
                  }`}
                >
                  {b === MY_DEVICES ? "★" : b.charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-xs font-semibold">{b}</span>
                  <span className="block text-[10px] text-slate-500">
                    {list.length} model{list.length === 1 ? "" : "s"}
                    {hasActive ? " · active" : ""}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {matches ? `${matches.length} match${matches.length === 1 ? "" : "es"}` : `${brand ?? ""} models`}
          </h3>
          {matches && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="flex items-center gap-0.5 text-[11px] text-cyan-300 hover:text-cyan-200"
            >
              <ChevronLeft className="h-3 w-3" /> All makers
            </button>
          )}
        </div>
        {models.length ? (
          <div className="grid grid-cols-2 gap-2">
            {models.map((p) => (
              <ModelCard
                key={p.id}
                preset={p}
                active={p.id === activeId}
                isUser={userPresetIds.includes(p.id)}
                showBrand={Boolean(matches)}
                onSelect={onSelect}
              />
            ))}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-slate-800 px-3 py-4 text-center text-[11px] text-slate-500">
            No model matches "{query}". Measure your phone and enter it in Pro mode.
          </p>
        )}
      </div>
    </div>
  );
}

/** <select> of every device, grouped by maker (Pro mode). */
export function DeviceSelect({ presets, userPresetIds = [], value, unsavedLabel, onChange, className = "" }) {
  const groups = useMemo(() => groupByBrand(presets, userPresetIds), [presets, userPresetIds]);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={className} aria-label="Device">
      {unsavedLabel && <option value={value}>{unsavedLabel}</option>}
      {groups.map(([brand, list]) => (
        <optgroup key={brand} label={brand}>
          {list.map((p) => (
            <option key={p.id} value={p.id}>
              {cleanDeviceName(p.name)}
              {p.year ? ` (${p.year})` : ""}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
