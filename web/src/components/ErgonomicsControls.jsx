import React from "react";
import { SliderField, ToggleRow } from "./Fields.jsx";

/**
 * Hand-feel details of the bumper (Pro > Tolerances): the outer chamfer around port openings,
 * horizontal grip grooves on the long side walls, and the unibody's flex slits beside the button
 * covers. Every bound comes from `limits` (fitLimits.js, mirroring params.py); the server still
 * validates the whole design. Missing keys (projects saved before these settings existed) show
 * the engine's defaults.
 */
export default function ErgonomicsControls({ config, limits, updateConfig }) {
  const s = config.style;
  const set = (key, immediate = false) => (v) =>
    updateConfig((c) => {
      c.style[key] = v;
      return c;
    }, immediate);
  const own = (config.ports || []).filter((p) => p.chamfer !== null && p.chamfer !== undefined).length;

  return (
    <section className="space-y-3 border-t border-slate-800 pt-4" aria-label="Grip and openings">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">Grip & Openings</h2>
      <SliderField
        label="Port opening chamfer"
        value={s.port_chamfer ?? 0.6}
        min={limits.port_chamfer[0]}
        max={limits.port_chamfer[1]}
        step={0.05}
        hint={
          "Outer 45° flare around the charging port and speaker openings so a cable plug clears the case. " +
          (own ? `${own} opening${own === 1 ? " has its" : "s have their"} own chamfer (Device tab).` : "0 = straight-walled.")
        }
        onChange={set("port_chamfer")}
      />
      <ToggleRow
        label="Grip grooves"
        hint="Horizontal V-grooves on the long side walls, kept clear of buttons and openings"
        checked={s.grip_ribs ?? false}
        onChange={set("grip_ribs", true)}
      />
      {s.grip_ribs && (
        <SliderField
          label="Grip groove depth"
          value={s.grip_rib_depth ?? 0.35}
          min={limits.grip_rib_depth[0]}
          max={limits.grip_rib_depth[1]}
          step={0.05}
          hint="Leaves at least 0.6 mm of wall behind each groove"
          onChange={set("grip_rib_depth")}
        />
      )}
      <ToggleRow
        label="Flexible unibody buttons"
        hint="One-piece case only: two slits beside each button cover so it presses in more easily"
        checked={s.compliant_buttons ?? true}
        onChange={set("compliant_buttons", true)}
      />
    </section>
  );
}
