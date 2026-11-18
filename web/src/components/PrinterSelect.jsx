import React from "react";
import { Printer } from "lucide-react";

// Printer profile picker. The selected profile drives the bed view, part layout, plate checks,
// 3MF export and whether the print-in-place export is offered.
export default function PrinterSelect({ printers, value, onChange }) {
  if (!printers.length) return null;
  const current = printers.find((p) => p.id === value);
  return (
    <label
      className="flex items-center gap-1.5 rounded-lg border border-slate-700/80 bg-slate-800/80 px-2 py-1 text-xs text-slate-300"
      title={current ? `${current.bed_x} × ${current.bed_y} mm plate\nSource: ${current.source}` : undefined}
    >
      <Printer className="h-3.5 w-3.5 text-cyan-400" />
      <select
        aria-label="Printer profile"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent text-xs font-medium text-slate-100 outline-none"
      >
        {printers.map((p) => (
          <option key={p.id} value={p.id} className="bg-slate-900">
            {p.name}
          </option>
        ))}
      </select>
    </label>
  );
}
