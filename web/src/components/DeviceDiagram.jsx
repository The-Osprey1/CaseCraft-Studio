import React from "react";

const ACCENT = "#22d3ee";
const MUTED = "#64748b";
const BODY = "#1e293b";

function sideRect(side, a0, len, W, L, depth, out) {
  // a0/len measured like button `pos`: from the top (left/right) or front-view left (top/bottom)
  switch (side) {
    case "left":
      return { x: out ? -depth - 0.4 : -depth / 2, y: a0, w: depth, h: len };
    case "right":
      return { x: out ? W + 0.4 : W - depth / 2, y: a0, w: depth, h: len };
    case "top":
      return { x: a0, y: out ? -depth - 0.4 : -depth / 2, w: len, h: depth };
    default:
      return { x: a0, y: out ? L + 0.4 : L - depth / 2, w: len, h: depth };
  }
}

function portStart(pt, W, L) {
  // port `center`: signed offset from the phone centre along its edge (+X = right seen from the
  // front for top/bottom, +Y = towards the top for left/right) -> distance from the top / left
  return pt.side === "left" || pt.side === "right" ? L / 2 - pt.center - pt.width / 2 : W / 2 + pt.center - pt.width / 2;
}

/**
 * Live sketch of the device as entered: the front (buttons and port openings at their real
 * positions) and the back (camera island or plateau, MagSafe ring). The field being edited is
 * drawn in cyan (`highlight`: "body" | "camera" | "button:i" | "port:i" | "magsafe").
 */
export default function DeviceDiagram({ config, highlight }) {
  if (!config?.body) return null;
  const { width: W, length: L, corner_radius: R } = config.body;
  if (!(W > 0 && L > 0)) return null;
  const r = Math.max(0, Math.min(R || 0, W / 2, L / 2));
  const pad = 5;
  const vb = `${-pad} ${-pad} ${W + 2 * pad} ${L + 2 * pad}`;
  const hl = (key) => highlight === key;
  const stroke = (key) => (hl(key) ? ACCENT : MUTED);
  const cam = config.camera || {};
  const style = config.style || {};

  const outline = (
    <rect
      x={0}
      y={0}
      width={W}
      height={L}
      rx={r}
      fill={BODY}
      stroke={hl("body") ? ACCENT : "#94a3b8"}
      strokeWidth={hl("body") ? 0.9 : 0.5}
    />
  );

  return (
    <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
      <figure className="flex flex-col items-center gap-1">
        <svg viewBox={vb} className="h-48 w-auto max-w-full" role="img" aria-label="Device seen from the front">
          {outline}
          <rect x={2.4} y={2.4} width={W - 4.8} height={L - 4.8} rx={Math.max(0, r - 2.4)} fill="#0b1220" stroke="#334155" strokeWidth={0.3} />
          {(config.buttons || []).map((b, i) => {
            const s = sideRect(b.side, b.pos, b.length, W, L, 1.4, true);
            return (
              <rect key={`b${i}`} {...{ x: s.x, y: s.y, width: s.w, height: s.h }} rx={0.6}
                fill={hl(`button:${i}`) ? ACCENT : "#94a3b8"} />
            );
          })}
          {(config.ports || []).map((pt, i) => {
            const s = sideRect(pt.side, portStart(pt, W, L), pt.width, W, L, 2.2, false);
            return (
              <rect key={`p${i}`} {...{ x: s.x, y: s.y, width: s.w, height: s.h }} rx={1}
                fill={hl(`port:${i}`) ? ACCENT : "#020617"} stroke={hl(`port:${i}`) ? ACCENT : "#475569"} strokeWidth={0.3} />
            );
          })}
        </svg>
        <figcaption className="text-[10px] text-slate-400">Front · buttons &amp; ports</figcaption>
      </figure>
      <figure className="flex flex-col items-center gap-1">
        <svg viewBox={vb} className="h-48 w-auto max-w-full" role="img" aria-label="Device seen from the back">
          {outline}
          {style.magsafe_ring && (
            <g fill="none" stroke={stroke("magsafe")} strokeWidth={0.6} strokeDasharray="2 1.5">
              <circle cx={W / 2} cy={L / 2 - (style.magsafe_offset_y || 0)} r={27.2} />
              <circle cx={W / 2} cy={L / 2 - (style.magsafe_offset_y || 0)} r={22.8} />
            </g>
          )}
          {cam.width > 0 && cam.height > 0 && (
            <rect
              x={cam.x}
              y={cam.y}
              width={cam.width}
              height={cam.height}
              rx={Math.max(0, Math.min(cam.radius || 0, cam.width / 2, cam.height / 2))}
              fill={hl("camera") ? "rgba(34,211,238,0.25)" : "rgba(148,163,184,0.18)"}
              stroke={hl("camera") ? ACCENT : "#94a3b8"}
              strokeWidth={0.6}
              strokeDasharray={cam.ring === false ? "1.6 1.2" : undefined}
            />
          )}
        </svg>
        <figcaption className="text-[10px] text-slate-400">
          Back · {cam.ring === false ? "open camera cut-out" : "camera ring"}
        </figcaption>
      </figure>
      <p className="col-span-2 text-center font-mono text-[10px] text-slate-500">
        {L} × {W} × {config.body.thickness} mm · corner R{R}
      </p>
    </div>
  );
}
