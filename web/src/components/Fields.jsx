import React from "react";

export function NumberField({ label, value, onChange, step = 0.1, min, max, unit = "mm" }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-slate-400">{label}</span>
      <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 focus-within:border-cyan-500">
        <input
          type="number"
          step={step}
          min={min}
          max={max}
          value={Number.isFinite(value) ? value : 0}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (!Number.isNaN(v)) onChange(v);
          }}
          className="w-full bg-transparent text-xs font-mono text-slate-100 outline-none"
        />
        {unit && <span className="ml-1 text-[10px] text-slate-500">{unit}</span>}
      </div>
    </label>
  );
}

const decimals = (step) => (step >= 1 ? 0 : step >= 0.1 ? 1 : 2);

export function SliderField({ label, value, onChange, min, max, step = 0.05, unit = "mm", hint }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300">{label}</span>
        <span className="font-mono text-cyan-300">
          {Number(value).toFixed(decimals(step))} {unit}
        </span>
      </div>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="h-1.5 w-full cursor-pointer rounded-lg bg-slate-800 accent-cyan-400"
      />
      {hint && <p className="text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}

/** One-of-n choice as a row of buttons (radio semantics). */
export function Segmented({ label, options, value, onChange, hint }) {
  return (
    <div className="space-y-1.5" role="radiogroup" aria-label={label}>
      <span className="text-xs font-medium text-slate-300">{label}</span>
      <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
        {options.map((o) => {
          const active = value === o.id;
          return (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(o.id)}
              className={`rounded-lg border px-2 py-1.5 text-xs font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
                active
                  ? "border-cyan-400 bg-cyan-500/15 text-cyan-100"
                  : "border-slate-800 bg-slate-950/60 text-slate-400 hover:text-slate-200"
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      {hint && <p className="text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
}

export function ToggleRow({ label, hint, checked, onChange }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-3.5 py-2.5">
      <span>
        <span className="block text-xs font-medium text-slate-200">{label}</span>
        {hint && <span className="block text-[11px] text-slate-400">{hint}</span>}
      </span>
      <input
        type="checkbox"
        checked={Boolean(checked)}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 shrink-0 accent-cyan-400"
      />
    </label>
  );
}
