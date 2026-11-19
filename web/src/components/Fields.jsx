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

export function SliderField({ label, value, onChange, min, max, step = 0.05, unit = "mm", hint }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300">{label}</span>
        <span className="font-mono text-cyan-300">
          {Number(value).toFixed(step >= 1 ? 0 : 2)} {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="h-1.5 w-full cursor-pointer rounded-lg bg-slate-800 accent-cyan-400"
      />
      {hint && <p className="text-[10px] text-slate-500">{hint}</p>}
    </div>
  );
}
