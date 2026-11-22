import React, { useEffect, useId, useRef, useState } from "react";

const fmt = (v) => (Number.isFinite(v) ? String(Math.round(v * 1e4) / 1e4) : "");

/**
 * Number input you can actually type into: the text is kept as typed (so "-", "1." or an empty
 * field while retyping are fine), a value is committed only once it parses and lies within
 * [min, max], and an out-of-range or unparsable entry is flagged instead of being sent to the
 * CAD engine. Enter commits, Escape restores the current value. `onFocusChange` lets a parent
 * highlight what is being edited (e.g. on a device diagram).
 */
export function NumberField({ label, value, onChange, step = 0.1, min, max, unit = "mm", hint, onFocusChange }) {
  const id = useId();
  const [text, setText] = useState(fmt(value));
  const [focused, setFocused] = useState(false);
  const focusedRef = useRef(false);
  useEffect(() => {
    if (!focusedRef.current) setText(fmt(value));
  }, [value]);

  const parsed = text.trim() === "" ? NaN : Number(text.replace(",", "."));
  const typing = focused && /^-?\.?$/.test(text.trim()); // "", "-" or "." on the way to a number
  const problem = typing
    ? null
    : !Number.isFinite(parsed)
    ? "Enter a number"
    : min !== undefined && parsed < min
    ? `Minimum ${min} ${unit}`.trim()
    : max !== undefined && parsed > max
    ? `Maximum ${max} ${unit}`.trim()
    : null;

  const update = (next) => {
    setText(next);
    const v = next.trim() === "" ? NaN : Number(next.replace(",", "."));
    if (Number.isFinite(v) && (min === undefined || v >= min) && (max === undefined || v <= max) && v !== value) {
      onChange(v);
    }
  };

  return (
    <label className="flex flex-col gap-1" htmlFor={id}>
      <span className="text-[11px] text-slate-400">{label}</span>
      <div
        className={`flex items-center rounded-lg border bg-slate-950 px-2.5 py-1.5 ${
          problem ? "border-rose-500/70" : "border-slate-800 focus-within:border-cyan-500"
        }`}
      >
        <input
          id={id}
          type="text"
          inputMode="decimal"
          value={text}
          aria-invalid={Boolean(problem)}
          onChange={(e) => update(e.target.value)}
          onFocus={() => {
            focusedRef.current = true;
            setFocused(true);
            onFocusChange?.(true);
          }}
          onBlur={() => {
            focusedRef.current = false;
            setFocused(false);
            onFocusChange?.(false);
            if (problem || typing) setText(fmt(value)); // abandon an unusable entry
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setText(fmt(value));
              e.currentTarget.blur();
            } else if (e.key === "Enter") {
              e.currentTarget.blur();
            } else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && Number.isFinite(parsed)) {
              e.preventDefault();
              const k = e.shiftKey ? 10 : 1;
              let v = parsed + (e.key === "ArrowUp" ? step : -step) * k;
              if (min !== undefined) v = Math.max(min, v);
              if (max !== undefined) v = Math.min(max, v);
              update(fmt(v));
            }
          }}
          className="w-full min-w-0 bg-transparent text-xs font-mono text-slate-100 outline-none"
        />
        {unit && <span className="ml-1 text-[10px] text-slate-500">{unit}</span>}
      </div>
      {problem ? (
        <span className="text-[10px] text-rose-300">{problem}</span>
      ) : (
        hint && <span className="text-[10px] text-slate-500">{hint}</span>
      )}
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
