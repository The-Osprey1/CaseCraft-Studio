import React from "react";

// Unobtrusive verification status of a device preset (provenance, not a guarantee of fit).
const LEVELS = {
  approximate: { label: "Approx. dims", cls: "border-amber-500/30 bg-amber-500/10 text-amber-300" },
  dimensionally_verified: { label: "Dims verified", cls: "border-sky-500/30 bg-sky-500/10 text-sky-300" },
  physically_fit_tested: { label: "Fit-tested", cls: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" },
};

export function verificationTitle(v) {
  if (!v) return "";
  return [
    `Dimensions: ${v.level.replaceAll("_", " ")}`,
    `Physical fit test: ${v.fit_test}`,
    v.source && `Source: ${v.source}`,
    v.unverified_features?.length && `Unverified: ${v.unverified_features.join(", ")}`,
    v.notes,
  ]
    .filter(Boolean)
    .join("\n");
}

export default function DeviceBadge({ verification, className = "" }) {
  const v = verification || { level: "approximate", fit_test: "untested" };
  const info = LEVELS[v.level] || LEVELS.approximate;
  return (
    <span
      title={verificationTitle(v)}
      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium ${info.cls} ${className}`}
    >
      {info.label}
    </span>
  );
}
