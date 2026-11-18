import React from "react";

export default function CrossSectionDiagram({ clearances, style }) {
  const w = Number(style.frame_wall ?? 1.6).toFixed(2);
  const bp = Number(style.backplate_thickness ?? 1.8).toFixed(2);
  const gd = Number(style.groove_depth ?? 0.9).toFixed(2);
  const se = Number(style.snap_engage ?? 0.6).toFixed(2);
  const lip = Number(style.front_lip ?? 1.2).toFixed(2);
  const o = Number(clearances.frame_to_phone_offset ?? 0.25).toFixed(2);
  const sc = Number(clearances.backplate_snap_clearance ?? 0.15).toFixed(2);
  const bc = Number(clearances.button_clearance ?? 0.2).toFixed(2);
  const cc = Number(clearances.camera_ring_clearance ?? 0.15).toFixed(2);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-cyan-400">
          Mechanical Cross-Sections (Live)
        </span>
        <span className="text-[10px] text-slate-400">Print Orientation: Back-Down (Z=0)</span>
      </div>

      {/* 1. Backplate Tongue-and-Groove Lock */}
      <svg viewBox="0 0 340 135" className="w-full rounded bg-slate-950/90 border border-slate-800/80">
        <text x="8" y="14" fill="#94a3b8" fontSize="9" fontWeight="600">
          1. BACKPLATE SNAP JOINT (45° OVERHANG-FREE)
        </text>
        {/* Build plate Z=0 line */}
        <line x1="10" y1="120" x2="330" y2="120" stroke="#334155" strokeWidth="1" strokeDasharray="3 3" />
        <text x="12" y="131" fill="#64748b" fontSize="8">Build Plate Z = 0</text>

        {/* Phone Body ghost */}
        <rect x="200" y="34" width="115" height="60" rx="4" fill="#1e293b" stroke="#475569" strokeDasharray="2 2" />
        <text x="257" y="67" textAnchor="middle" fill="#64748b" fontSize="9">PHONE</text>

        {/* TPU Bumper Frame (Back-Down) */}
        <path
          d="M 110 120 L 110 24 Q 110 20 114 20 L 166 20 Q 170 20 175 24 L 218 35 L 218 42 L 185 42 L 185 88 L 154 88 L 154 106 L 175 106 L 175 120 Z"
          fill="#0e7490"
          fillOpacity="0.45"
          stroke="#22d3ee"
          strokeWidth="1.3"
        />
        <text x="132" y="64" fill="#67e8f9" fontSize="8" fontWeight="600" textAnchor="middle">TPU</text>
        <text x="132" y="74" fill="#67e8f9" fontSize="8" fontWeight="600" textAnchor="middle">FRAME</text>

        {/* Rigid Backplate with 45 deg chamfered tongue */}
        <path
          d="M 180 120 L 180 104 L 159 104 L 159 95 L 168 90 L 315 90 L 315 120 Z"
          fill="#6366f1"
          fillOpacity="0.45"
          stroke="#a5b4fc"
          strokeWidth="1.3"
        />
        <text x="245" y="108" fill="#c7d2fe" fontSize="8.5" fontWeight="600" textAnchor="middle">
          BACKPLATE ({bp} mm)
        </text>

        {/* Callouts */}
        <text x="66" y="48" fill="#cbd5e1" fontSize="8">Wall: {w}mm</text>
        <line x1="100" y1="45" x2="110" y2="45" stroke="#64748b" strokeWidth="0.8" />
        <text x="205" y="25" fill="#cbd5e1" fontSize="8">Lip: {lip}mm (45°)</text>
        <text x="42" y="99" fill="#fbbf24" fontSize="8">Groove: {gd}mm</text>
        <line x1="94" y1="96" x2="154" y2="96" stroke="#fbbf24" strokeWidth="0.8" strokeDasharray="2 2" />
        <text x="42" y="112" fill="#34d399" fontSize="8">Snap: {se}mm / Clr: {sc}</text>
        <text x="236" y="85" fill="#94a3b8" fontSize="7.5">Phone gap: {o}mm</text>
      </svg>

      {/* 2. Floating Button & Camera Ring */}
      <svg viewBox="0 0 340 102" className="w-full rounded bg-slate-950/90 border border-slate-800/80">
        {/* Left: Button capture pocket */}
        <text x="8" y="14" fill="#94a3b8" fontSize="8.5" fontWeight="600">2. CAPTURED BUTTON</text>
        <rect x="18" y="26" width="38" height="22" fill="#0e7490" fillOpacity="0.4" stroke="#22d3ee" />
        <rect x="18" y="72" width="38" height="22" fill="#0e7490" fillOpacity="0.4" stroke="#22d3ee" />
        <rect x="40" y="42" width="16" height="36" fill="#0f172a" stroke="#22d3ee" strokeDasharray="2 1" />
        {/* Rigid button */}
        <path
          d="M 8 51 L 42 51 L 42 45 L 54 45 L 54 55 L 62 55 L 62 65 L 54 65 L 54 75 L 42 75 L 42 69 L 8 69 Z"
          fill="#f59e0b"
          fillOpacity="0.6"
          stroke="#fcd34d"
          strokeWidth="1.2"
        />
        <text x="72" y="46" fill="#fcd34d" fontSize="8">Flange locked</text>
        <text x="72" y="57" fill="#cbd5e1" fontSize="8">Clr: {bc} mm</text>
        <text x="72" y="68" fill="#94a3b8" fontSize="7.5">Cap-down print</text>

        {/* Divider */}
        <line x1="168" y1="10" x2="168" y2="94" stroke="#1e293b" strokeWidth="1" />

        {/* Right: Camera ring press-fit */}
        <text x="178" y="14" fill="#94a3b8" fontSize="8.5" fontWeight="600">3. CAMERA RING SNAP</text>
        {/* Backplate edges */}
        <rect x="182" y="56" width="54" height="22" fill="#6366f1" fillOpacity="0.4" stroke="#a5b4fc" />
        <rect x="278" y="56" width="52" height="22" fill="#6366f1" fillOpacity="0.4" stroke="#a5b4fc" />
        {/* Ring */}
        <path
          d="M 218 32 L 296 32 L 296 46 L 281 46 L 281 74 L 274 74 L 274 46 L 240 46 L 240 74 L 233 74 L 233 46 L 218 46 Z"
          fill="#ec4899"
          fillOpacity="0.55"
          stroke="#f472b6"
          strokeWidth="1.2"
        />
        <text x="257" y="92" textAnchor="middle" fill="#cbd5e1" fontSize="8">
          Press Clr: {cc}mm · Bezel-down
        </text>
      </svg>
    </div>
  );
}
