import React from "react";

function luminance(hex = "#000000") {
  const n = parseInt(String(hex).replace("#", "").slice(0, 6), 16) || 0;
  return (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
}

/**
 * The back of the case drawn from the server's 2D path data (patterns.pattern_preview /
 * pattern_gallery), in the user's filament colours: bumper rim, backplate, camera ring and the
 * cut-outs. Through-cuts show the phone behind them (light on a dark plate, dark on a light
 * one), a deboss reads as a shaded recess and an inlay takes the inlay colour. Loose pieces
 * (rose) and too-thin ligaments (amber) are drawn on top when `showIssues`.
 * `crop="middle"` frames a square swatch through the middle of the plate (gallery thumbnails).
 */
export default function PlatePreview({ frame, cuts, colors, mode = "through", showIssues = false, issues,
                                       dim = false, crop, className = "", label }) {
  if (!frame?.viewBox) return <div className={`rounded-md bg-slate-800/40 ${className}`} aria-hidden />;
  let [x, y, w, h] = frame.viewBox;
  if (crop === "middle") {
    y = -w / 2;
    h = w;
  }
  const thin = Math.max(w, h) / 220;
  const darkPlate = luminance(colors.backplate) < 0.42;
  const hole = darkPlate ? "#a7b1bf" : "#1e2533";
  return (
    <svg
      viewBox={`${x} ${y} ${w} ${h}`}
      className={`${className} transition-opacity ${dim ? "opacity-45" : "opacity-100"}`}
      role="img"
      aria-label={label}
    >
      {/* the phone seen through the camera cut-out (a whole band for a camera plateau) */}
      {frame.camera && <path d={frame.camera} fill={hole} fillRule="evenodd" />}
      <path d={frame.frame} fill={colors.frame} fillRule="evenodd" />
      <path d={frame.plate} fill={colors.backplate} fillRule="evenodd" />
      {cuts && mode === "through" && <path d={cuts} fill={hole} fillRule="evenodd" />}
      {cuts && mode === "deboss" && (
        <path d={cuts} fill={darkPlate ? "#ffffff" : "#000000"} fillOpacity={darkPlate ? 0.2 : 0.38} fillRule="evenodd" />
      )}
      {cuts && mode === "inlay" && <path d={cuts} fill={colors.inlay} fillRule="evenodd" />}
      {frame.ring && <path d={frame.ring} fill={colors.camera_ring} fillRule="evenodd" />}
      {frame.magsafe && (
        <path
          d={frame.magsafe}
          fill="none"
          stroke={darkPlate ? "#cbd5e1" : "#334155"}
          strokeOpacity={0.7}
          strokeWidth={thin * 1.2}
          strokeDasharray={`${thin * 5} ${thin * 4}`}
          fillRule="evenodd"
        />
      )}
      {showIssues && issues?.thin && <path d={issues.thin} fill="#f59e0b" stroke="#f59e0b" strokeWidth={thin} />}
      {showIssues && issues?.islands && (
        <path d={issues.islands} fill="#f43f5e" stroke="#fecdd3" strokeWidth={thin} fillRule="evenodd" />
      )}
    </svg>
  );
}
