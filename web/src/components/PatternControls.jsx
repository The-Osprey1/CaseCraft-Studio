import React from "react";
import { Upload } from "lucide-react";
import { FINISH_MODES, PATTERN_CARDS, SAMPLE_SVGS } from "../constants.jsx";
import { SliderField } from "./Fields.jsx";

// Pattern type cards, finish mode, per-pattern parameters and the MagSafe pocket toggle.
// Moved from App.jsx (renderPatternControls); behaviour unchanged.
export default function PatternControls({ config, updateConfig, uiMode }) {
  const handleSelectPatternType = (ptype) => {
    updateConfig((c) => {
      c.pattern.type = ptype;
      if (ptype === "hex") {
        c.pattern.params = { pitch: c.pattern.params?.pitch || 9.0 };
      } else if (ptype === "voronoi") {
        c.pattern.params = {
          pitch: c.pattern.params?.pitch || 11.0,
          seed: c.pattern.params?.seed ?? 42,
        };
      } else if (ptype === "waves") {
        c.pattern.params = {
          pitch: c.pattern.params?.pitch || 7.0,
          amplitude: c.pattern.params?.amplitude ?? 3.5,
          wavelength: c.pattern.params?.wavelength ?? 28.0,
        };
      } else if (ptype === "grid") {
        c.pattern.params = {
          pitch: c.pattern.params?.pitch || 8.5,
          angle: c.pattern.params?.angle ?? 45.0,
        };
      } else if (ptype === "text") {
        c.pattern.params = {
          text: c.pattern.params?.text || "CASECRAFT",
          size: c.pattern.params?.size ?? 0.65,
          rotation: c.pattern.params?.rotation ?? 0,
          bold: c.pattern.params?.bold ?? true,
        };
      } else if (ptype === "svg") {
        c.pattern.params = {
          svg: c.pattern.params?.svg || SAMPLE_SVGS.star.svg,
          size: c.pattern.params?.size ?? 0.6,
        };
      }
      return c;
    }, true);
  };

  const handleSvgUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      updateConfig((c) => {
        c.pattern.type = "svg";
        c.pattern.params = {
          ...c.pattern.params,
          svg: String(reader.result || ""),
          size: c.pattern.params?.size ?? 0.65,
        };
        return c;
      }, true);
    };
    reader.readAsText(file);
  };

    if (!config) return null;
    return (
      <div className="space-y-4">
        {/* Visual Pattern Cards */}
        <div className="grid grid-cols-2 gap-2.5">
          {PATTERN_CARDS.map((card) => {
            const active = config.pattern.type === card.id;
            return (
              <button
                key={card.id}
                type="button"
                onClick={() => handleSelectPatternType(card.id)}
                className={`rounded-xl border p-3 text-left transition-all ${
                  active
                    ? "border-cyan-400 bg-cyan-500/10 ring-1 ring-cyan-400/25"
                    : "border-slate-800 bg-slate-900/70 hover:border-slate-700"
                }`}
              >
                <div
                  className={`mb-2 flex h-9 w-9 items-center justify-center rounded-lg ${
                    active
                      ? "bg-cyan-500/20 text-cyan-300"
                      : "bg-slate-800 text-slate-400"
                  }`}
                >
                  {card.icon}
                </div>
                <div className="text-xs font-semibold text-white">
                  {card.name}
                </div>
                <div className="mt-0.5 text-[11px] leading-snug text-slate-400">
                  {card.desc}
                </div>
              </button>
            );
          })}
        </div>

        {/* Finish / Extrusion Pills */}
        {config.pattern.type !== "solid" && (
          <div className="space-y-3 border-t border-slate-800/80 pt-4">
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-slate-300">
                Backplate Finish
              </span>
              <div className="grid grid-cols-3 gap-2">
                {FINISH_MODES.map((m) => {
                  const active = config.pattern.mode === m.id;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() =>
                        updateConfig((c) => {
                          c.pattern.mode = m.id;
                          return c;
                        }, true)
                      }
                      className={`rounded-lg border px-2.5 py-2 text-center transition ${
                        active
                          ? "border-cyan-400 bg-cyan-500/15 text-cyan-200"
                          : "border-slate-800 bg-slate-950/60 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <div className="text-xs font-semibold">{m.label}</div>
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] text-slate-500">
                {FINISH_MODES.find((m) => m.id === config.pattern.mode)?.desc}
              </p>
            </div>

            {/* Contextual Pattern Settings */}
            {config.pattern.type === "hex" && (
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                <SliderField
                  label="Hex Cell Spacing (Pitch)"
                  value={config.pattern.params?.pitch ?? 9.0}
                  min={5.5}
                  max={16.0}
                  step={0.5}
                  hint="Smaller pitch = finer honeycomb mesh"
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, pitch: v };
                      return c;
                    })
                  }
                />
              </div>
            )}

            {config.pattern.type === "voronoi" && (
              <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                <SliderField
                  label="Voronoi Cell Spacing"
                  value={config.pattern.params?.pitch ?? 11.0}
                  min={7.0}
                  max={18.0}
                  step={0.5}
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, pitch: v };
                      return c;
                    })
                  }
                />
                <SliderField
                  label="Pattern Seed"
                  value={config.pattern.params?.seed ?? 42}
                  min={1}
                  max={99}
                  step={1}
                  unit=""
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, seed: v };
                      return c;
                    })
                  }
                />
              </div>
            )}

            {config.pattern.type === "waves" && (
              <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                <SliderField
                  label="Wave Spacing (Pitch)"
                  value={config.pattern.params?.pitch ?? 7.0}
                  min={4.5}
                  max={14.0}
                  step={0.5}
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, pitch: v };
                      return c;
                    })
                  }
                />
                <SliderField
                  label="Wave Amplitude"
                  value={config.pattern.params?.amplitude ?? 3.5}
                  min={1.0}
                  max={8.0}
                  step={0.5}
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, amplitude: v };
                      return c;
                    })
                  }
                />
              </div>
            )}

            {config.pattern.type === "grid" && (
              <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                <SliderField
                  label="Grid Spacing (Pitch)"
                  value={config.pattern.params?.pitch ?? 8.5}
                  min={5.5}
                  max={16.0}
                  step={0.5}
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, pitch: v };
                      return c;
                    })
                  }
                />
                <SliderField
                  label="Grid Angle"
                  value={config.pattern.params?.angle ?? 45.0}
                  min={0}
                  max={90}
                  step={15}
                  unit="°"
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, angle: v };
                      return c;
                    })
                  }
                />
              </div>
            )}

            {config.pattern.type === "text" && (
              <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-slate-300">
                    Monogram Text
                  </span>
                  <input
                    type="text"
                    maxLength={18}
                    value={config.pattern.params?.text ?? "CASECRAFT"}
                    onChange={(e) =>
                      updateConfig((c) => {
                        c.pattern.params = {
                          ...c.pattern.params,
                          text: e.target.value,
                        };
                        return c;
                      })
                    }
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-white outline-none focus:border-cyan-400"
                  />
                </label>
                <SliderField
                  label="Text Scale"
                  value={config.pattern.params?.size ?? 0.65}
                  min={0.25}
                  max={0.9}
                  step={0.05}
                  unit="×"
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, size: v };
                      return c;
                    })
                  }
                />
                <SliderField
                  label="Rotation"
                  value={config.pattern.params?.rotation ?? 0}
                  min={-90}
                  max={90}
                  step={5}
                  unit="°"
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, rotation: v };
                      return c;
                    })
                  }
                />
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(config.pattern.params?.bold ?? true)}
                    onChange={(e) =>
                      updateConfig((c) => {
                        c.pattern.params = {
                          ...c.pattern.params,
                          bold: e.target.checked,
                        };
                        return c;
                      }, true)
                    }
                    className="accent-cyan-400"
                  />
                  Bold Font Weight
                </label>
              </div>
            )}

            {config.pattern.type === "svg" && (
              <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-cyan-500/50 bg-cyan-500/5 px-3 py-2.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/10 transition">
                  <Upload className="h-3.5 w-3.5" />
                  Upload Custom .SVG Artwork
                  <input
                    type="file"
                    accept=".svg,image/svg+xml"
                    onChange={handleSvgUpload}
                    className="hidden"
                  />
                </label>

                <div className="space-y-1.5">
                  <span className="text-[11px] text-slate-400">
                    Quick Vector Emblems
                  </span>
                  <div className="grid grid-cols-3 gap-1.5">
                    {Object.entries(SAMPLE_SVGS).map(([k, item]) => (
                      <button
                        key={k}
                        type="button"
                        onClick={() =>
                          updateConfig((c) => {
                            c.pattern.params = {
                              ...c.pattern.params,
                              svg: item.svg,
                              size: c.pattern.params?.size ?? 0.6,
                            };
                            return c;
                          }, true)
                        }
                        className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-[11px] text-slate-300 hover:border-cyan-500 transition"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>

                <SliderField
                  label="Artwork Scale"
                  value={config.pattern.params?.size ?? 0.6}
                  min={0.25}
                  max={0.9}
                  step={0.05}
                  unit="×"
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.params = { ...c.pattern.params, size: v };
                      return c;
                    })
                  }
                />
              </div>
            )}

            {config.pattern.mode === "through" &&
              (config.pattern.type === "text" || config.pattern.type === "svg") && (
                <label className="flex cursor-pointer items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 px-3.5 py-2.5">
                  <div>
                    <div className="text-xs font-medium text-slate-200">
                      Auto Stencil Bridges
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Anchors inner islands of O / A / B cutouts
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={Boolean(config.pattern.stencil_bridges ?? true)}
                    onChange={(e) =>
                      updateConfig((c) => {
                        c.pattern.stencil_bridges = e.target.checked;
                        return c;
                      }, true)
                    }
                    className="h-4 w-4 accent-cyan-400"
                  />
                </label>
              )}

            {/* Advanced pattern parameters only in Pro Mode */}
            {uiMode === "pro" && (
              <div className="space-y-3 border-t border-slate-800/80 pt-3">
                <SliderField
                  label="Edge Margin"
                  value={config.pattern.margin}
                  min={1.5}
                  max={10.0}
                  step={0.5}
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.margin = v;
                      return c;
                    })
                  }
                />
                <SliderField
                  label="Min Web Ligament"
                  value={config.pattern.web}
                  min={1.0}
                  max={4.0}
                  step={0.1}
                  onChange={(v) =>
                    updateConfig((c) => {
                      c.pattern.web = v;
                      return c;
                    })
                  }
                />
                {config.pattern.mode !== "through" && (
                  <SliderField
                    label="Deboss / Inlay Depth"
                    value={config.pattern.depth}
                    min={0.4}
                    max={Math.max(0.4, (config.style?.backplate_thickness ?? 1.8) - 0.6)}
                    step={0.1}
                    onChange={(v) =>
                      updateConfig((c) => {
                        c.pattern.depth = v;
                        return c;
                      })
                    }
                  />
                )}
              </div>
            )}
          </div>
        )}

        {/* MagSafe Magnet Ring Pocket Toggle */}
        <label className="flex cursor-pointer items-center justify-between rounded-xl border border-slate-800 bg-slate-900/75 px-3.5 py-3">
          <div>
            <div className="text-xs font-semibold text-white">
              Internal MagSafe Ring Pocket
            </div>
            <div className="text-[11px] text-slate-400">
              {config.style?.magsafe_depth ?? 0.75} mm recessed 54/46 mm magnet ring + alignment tail
            </div>
          </div>
          <input
            type="checkbox"
            checked={Boolean(config.style?.magsafe_ring)}
            onChange={(e) =>
              updateConfig((c) => {
                c.style.magsafe_ring = e.target.checked;
                return c;
              }, true)
            }
            className="h-4 w-4 accent-cyan-400"
          />
        </label>
        {config.style?.magsafe_ring && (
          <SliderField
            label="MagSafe Ring Vertical Offset"
            value={config.style?.magsafe_offset_y ?? 0}
            min={-30}
            max={30}
            step={0.5}
            hint="Negative moves the ring toward the bottom. Match your phone's charging coil and keep clear of the camera."
            onChange={(v) =>
              updateConfig((c) => {
                c.style.magsafe_offset_y = v;
                return c;
              })
            }
          />
        )}
      </div>
    );
}
