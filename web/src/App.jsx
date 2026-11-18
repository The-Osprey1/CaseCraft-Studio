import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Check,
  Download,
  FileCode2,
  Grid3X3,
  Layers,
  Loader2,
  Palette,
  Plus,
  RefreshCw,
  Sliders,
  Smartphone,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
} from "lucide-react";
import Viewport3D from "./components/Viewport3D.jsx";
import CrossSectionDiagram from "./components/CrossSectionDiagram.jsx";

const SAMPLE_SVGS = {
  star: {
    label: "Star Emblem",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M50 5 L61 38 L95 38 L67 58 L78 92 L50 71 L22 92 L33 58 L5 38 L39 38 Z"/><circle cx="50" cy="50" r="8"/></svg>',
  },
  bolt: {
    label: "Lightning Bolt",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M58 4 L18 55 L46 55 L38 96 L82 42 L53 42 Z"/></svg>',
  },
  crest: {
    label: "Geometric Crest",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M50 6 L88 28 L88 72 L50 94 L12 72 L12 28 Z M50 22 L73 35 L73 65 L50 78 L27 65 L27 35 Z"/></svg>',
  },
};

const FILAMENT_THEMES = [
  {
    id: "bambu-orange",
    name: "Bambu Carbon",
    subtitle: "Charcoal TPU + Orange Accents",
    colors: {
      frame: "#181b20",
      backplate: "#2d333b",
      inlay: "#f97316",
      camera_ring: "#f97316",
      buttons: "#f97316",
    },
  },
  {
    id: "cyber-cyan",
    name: "Cyber Cyan",
    subtitle: "Midnight Navy + Neon Cyan",
    colors: {
      frame: "#0f172a",
      backplate: "#1e293b",
      inlay: "#06b6d4",
      camera_ring: "#22d3ee",
      buttons: "#22d3ee",
    },
  },
  {
    id: "stealth-matte",
    name: "Stealth Matte",
    subtitle: "Triple Black + Slate Ring",
    colors: {
      frame: "#111315",
      backplate: "#1c1f24",
      inlay: "#475569",
      camera_ring: "#3f444e",
      buttons: "#64748b",
    },
  },
  {
    id: "voron-racing",
    name: "Voron Racing",
    subtitle: "Jet Black + Crimson ABS",
    colors: {
      frame: "#141417",
      backplate: "#232329",
      inlay: "#ef4444",
      camera_ring: "#ef4444",
      buttons: "#ef4444",
    },
  },
  {
    id: "arctic-frost",
    name: "Arctic Frost",
    subtitle: "Storm Slate + Jade White",
    colors: {
      frame: "#334155",
      backplate: "#e2e8f0",
      inlay: "#38bdf8",
      camera_ring: "#0284c7",
      buttons: "#38bdf8",
    },
  },
  {
    id: "walnut-gold",
    name: "Walnut & Brass",
    subtitle: "Laser Wood + Silk Gold",
    colors: {
      frame: "#1c1917",
      backplate: "#78350f",
      inlay: "#eab308",
      camera_ring: "#eab308",
      buttons: "#eab308",
    },
  },
];

const BAMBU_SWATCHES = [
  { name: "Matte Charcoal", hex: "#1e293b" },
  { name: "Bambu Cyan", hex: "#06b6d4" },
  { name: "Bambu Orange", hex: "#f97316" },
  { name: "Jade White", hex: "#e2e8f0" },
  { name: "Crimson Red", hex: "#ef4444" },
  { name: "Bambu Green", hex: "#10b981" },
  { name: "Royal Indigo", hex: "#6366f1" },
  { name: "Gold Silk", hex: "#eab308" },
  { name: "Walnut Wood", hex: "#78350f" },
];

const PATTERN_CARDS = [
  {
    id: "hex",
    name: "Hexagon Mesh",
    desc: "Lightweight airflow honeycomb grid",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 2l5.2 3v6L12 14l-5.2-3V5L12 2z" />
        <path d="M6.8 11l5.2 3v6l-5.2 3-5.2-3v-6l5.2-3z" />
        <path d="M17.2 11l5.2 3v6l-5.2 3-5.2-3v-6l5.2-3z" />
      </svg>
    ),
  },
  {
    id: "voronoi",
    name: "Voronoi Cells",
    desc: "Organic cellular lattice geometry",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <polygon points="4,4 13,3 11,11 3,12" />
        <polygon points="13,3 21,6 19,15 11,11" />
        <polygon points="3,12 11,11 13,20 5,21" />
        <polygon points="11,11 19,15 20,21 13,20" />
      </svg>
    ),
  },
  {
    id: "waves",
    name: "Sine Waves",
    desc: "Flowing acoustic ribbon bands",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M2 8c3-4 6-4 9 0s6 4 11 0" />
        <path d="M2 14c3-4 6-4 9 0s6 4 11 0" />
        <path d="M2 20c3-4 6-4 9 0s6 4 11 0" />
      </svg>
    ),
  },
  {
    id: "grid",
    name: "Diamond Grid",
    desc: "Crisp angled lattice cross-mesh",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M12 2l8 10-8 10L4 12 12 2z" />
        <path d="M8 7l8 10M16 7L8 17" />
      </svg>
    ),
  },
  {
    id: "solid",
    name: "Solid Armor",
    desc: "Clean, full dust & impact shield",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="5" y="2" width="14" height="20" rx="3" />
        <rect x="8" y="5" width="4" height="4" rx="1" />
      </svg>
    ),
  },
  {
    id: "text",
    name: "Text Monogram",
    desc: "Custom lettering with stencil bridges",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 7V4h16v3M9 20h6M12 4v16" />
      </svg>
    ),
  },
  {
    id: "svg",
    name: "Vector SVG Art",
    desc: "Upload or pick vector emblem art",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    ),
  },
];

const CALIBRATION_PROFILES = [
  {
    id: "h3c",
    label: "H3C / Tool-Changer",
    desc: "Co-printed multi-head tolerances",
    clearances: {
      frame_to_phone_offset: 0.25,
      backplate_snap_clearance: 0.15,
      button_clearance: 0.2,
      camera_ring_clearance: 0.15,
    },
  },
  {
    id: "bambu_68d",
    label: "Bambu AMS (68D)",
    desc: "Rigid TPU 68D snap-fit clearances",
    clearances: {
      frame_to_phone_offset: 0.25,
      backplate_snap_clearance: 0.15,
      button_clearance: 0.2,
      camera_ring_clearance: 0.15,
    },
  },
  {
    id: "soft_95a",
    label: "Soft TPU 95A",
    desc: "Tighter snap grip for flexible 95A",
    clearances: {
      frame_to_phone_offset: 0.15,
      backplate_snap_clearance: 0.12,
      button_clearance: 0.22,
      camera_ring_clearance: 0.15,
    },
  },
];

const FINISH_MODES = [
  { id: "through", label: "Through-Cut", desc: "Open vents & laser-ready profile" },
  { id: "deboss", label: "Deboss", desc: "Recessed engraving on back face" },
  { id: "inlay", label: "AMS Inlay", desc: "2-color flush 3MF insert" },
];

const DEFAULT_VISIBLE = {
  frame: true,
  backplate: true,
  inlay: true,
  camera_ring: true,
  buttons: true,
};

function cleanDeviceName(name = "") {
  return name.replace(" (approx - verify with calipers)", "");
}

function NumberField({ label, value, onChange, step = 0.1, min, max, unit = "mm" }) {
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

function SliderField({ label, value, onChange, min, max, step = 0.05, unit = "mm", hint }) {
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

export default function App() {
  const [presets, setPresets] = useState([]);
  const [config, setConfig] = useState(null);
  const [preview, setPreview] = useState(null);

  // Progressive Disclosure: Simple Wizard (default) vs Pro CAD Mode
  const [uiMode, setUiMode] = useState("simple"); // 'simple' | 'pro'
  const [wizardStep, setWizardStep] = useState(1); // 1 | 2 | 3
  const [proTab, setProTab] = useState("calipers"); // 'calipers' | 'tolerances' | 'pattern' | 'colors'

  // Viewport HUD State
  const [viewMode, setViewMode] = useState("assembly"); // 'assembly' | 'bed' | 'svg'
  const [explode, setExplode] = useState(0);
  const [showPhoneGhost, setShowPhoneGhost] = useState(false);

  // Filament Colors & Visibility
  const [activeThemeId, setActiveThemeId] = useState(FILAMENT_THEMES[0].id);
  const [activeCalId, setActiveCalId] = useState("h3c");
  const [colors, setColors] = useState(FILAMENT_THEMES[0].colors);
  const [visibleGroups, setVisibleGroups] = useState(DEFAULT_VISIBLE);

  // Request Status
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(null); // null | 'full' | 'coupon'
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);

  const debounceRef = useRef(null);
  const requestIdRef = useRef(0);

  const runGenerate = useCallback(async (payload) => {
    if (!payload) return;
    const reqId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/generate-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${res.status})`);
      }
      const data = await res.json();
      if (reqId === requestIdRef.current) {
        setPreview(data);
        setDirty(false);
      }
    } catch (err) {
      if (reqId === requestIdRef.current) {
        setError(err.message);
      }
    } finally {
      if (reqId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/presets");
        if (!res.ok) throw new Error("Failed to load presets");
        const data = await res.json();
        setPresets(data.presets);
        const initial =
          data.presets.find((p) => p.id === data.default_id) || data.presets[0];
        if (initial) {
          const clone = structuredClone(initial);
          setConfig(clone);
          runGenerate(clone);
        }
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [runGenerate]);

  const updateConfig = useCallback(
    (updater, immediate = false) => {
      setConfig((prev) => {
        if (!prev) return prev;
        const next =
          typeof updater === "function"
            ? updater(structuredClone(prev))
            : updater;
        setDirty(true);
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(
          () => runGenerate(next),
          immediate ? 30 : 480
        );
        return next;
      });
    },
    [runGenerate]
  );

  const handleSelectPreset = (id) => {
    const found = presets.find((p) => p.id === id);
    if (!found) return;
    const next = structuredClone(found);
    if (config?.pattern) next.pattern = structuredClone(config.pattern);
    setConfig(next);
    setDirty(false);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    runGenerate(next);
  };

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

  const handleExportPart = async (partKey, filenameSuffix) => {
    if (!config) return;
    setExporting(partKey);
    setError(null);
    try {
      const res = await fetch(`/api/export-part?part=${partKey}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Part export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${config.id}_${filenameSuffix}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(null);
    }
  };

  const handleExportPresetJson = () => {
    if (!config) return;
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${config.id}_preset.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleImportPresetJson = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result || "{}"));
        setConfig(parsed);
        setDirty(false);
        runGenerate(parsed);
      } catch {
        setError("Invalid preset JSON file.");
      }
    };
    reader.readAsText(file);
  };

  const handleExportZip = async (coupon = false) => {
    if (!config) return;
    setExporting(coupon ? "coupon" : "full");
    setError(null);
    try {
      const res = await fetch(`/api/export-zip?coupon=${coupon}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = coupon
        ? `${config.id}_coupon_bundle.zip`
        : `${config.id}_casecraft_bundle.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(null);
    }
  };

  const handleDownloadLaserSvg = () => {
    if (!preview?.laser_svg || !config) return;
    const blob = new Blob([preview.laser_svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${config.id}_Laser_Backplate.svg`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
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

  const renderPatternControls = () => {
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
  };

  const hasInlay = Boolean(
    preview?.summary?.has_inlay ||
      preview?.parts?.some((p) => p.group === "inlay")
  );

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-950 text-slate-100 select-none">
      {/* ==================== CLEAN SINGLE-ROW HEADER ==================== */}
      <header className="z-20 flex min-h-14 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 bg-slate-900/85 px-4 py-2 backdrop-blur-md">
        {/* Left: Brand Identity + Device Pill */}
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-cyan-500/30 bg-gradient-to-br from-cyan-500/20 to-teal-500/10 text-cyan-400">
            <Box className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="whitespace-nowrap text-sm font-semibold tracking-tight text-white">
                CaseCraft Studio
              </h1>
              {config && (
                <span className="whitespace-nowrap rounded-full border border-cyan-500/25 bg-cyan-500/10 px-2 py-0.5 text-[11px] font-medium text-cyan-300">
                  {cleanDeviceName(config.name)}
                </span>
              )}
            </div>
            <p className="hidden xl:block text-[11px] text-slate-400">
              Modular 4-Part Snap-Fit CAD Generator
            </p>
          </div>
        </div>

        {/* Center: Simple Wizard vs Pro CAD Mode Toggle */}
        <div className="flex shrink-0 items-center rounded-xl border border-slate-800 bg-slate-950 p-1">
          <button
            type="button"
            onClick={() => setUiMode("simple")}
            className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1 text-xs font-medium transition ${
              uiMode === "simple"
                ? "bg-cyan-500 font-semibold text-slate-950 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Wand2 className="h-3.5 w-3.5" />
            Simple Wizard
          </button>
          <button
            type="button"
            onClick={() => setUiMode("pro")}
            className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1 text-xs font-medium transition ${
              uiMode === "pro"
                ? "bg-cyan-500 font-semibold text-slate-950 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Sliders className="h-3.5 w-3.5" />
            Pro CAD Mode
          </button>
        </div>

        {/* Right: Rebuild + Primary Export Actions */}
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={!config || loading}
            onClick={() => runGenerate(config)}
            className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-medium transition disabled:opacity-50 ${
              dirty
                ? "border-amber-500/50 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25"
                : "border-slate-700/80 bg-slate-800/80 text-slate-200 hover:bg-slate-800"
            }`}
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5 text-cyan-400" />
            )}
            {loading ? "Solving…" : "Rebuild"}
          </button>

          <button
            type="button"
            disabled={!config || exporting !== null}
            onClick={() => handleExportZip(true)}
            className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-700 bg-slate-800/90 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700/80 disabled:opacity-50 transition"
          >
            {exporting === "coupon" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5 text-amber-400" />
            )}
            10-Min Fit Coupon
          </button>

          <button
            type="button"
            disabled={!config || exporting !== null}
            onClick={() => handleExportZip(false)}
            className="flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 hover:bg-cyan-400 disabled:opacity-50 transition"
          >
            {exporting === "full" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            Export Slicer Bundle (.zip)
          </button>
        </div>
      </header>

      {/* ==================== MAIN TWO-PANE WORKSPACE ==================== */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* LEFT PANE */}
        <aside className="flex w-[350px] xl:w-[410px] shrink-0 flex-col border-r border-slate-800/80 bg-slate-900/45">
          {uiMode === "simple" ? (
            /* -------------------- SIMPLE 3-STEP WIZARD -------------------- */
            <>
              <div className="border-b border-slate-800/80 bg-slate-900/60 px-4 py-3">
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { step: 1, title: "1. Phone", sub: "Select Model" },
                    { step: 2, title: "2. Style", sub: "Pattern & Finish" },
                    { step: 3, title: "3. Export", sub: "Colors & Print" },
                  ].map((item) => {
                    const active = wizardStep === item.step;
                    const done = wizardStep > item.step;
                    return (
                      <button
                        key={item.step}
                        type="button"
                        onClick={() => setWizardStep(item.step)}
                        className={`rounded-xl border p-2.5 text-left transition-all ${
                          active
                            ? "border-cyan-500/60 bg-cyan-500/10 text-white shadow-sm"
                            : done
                            ? "border-slate-700/70 bg-slate-800/50 text-slate-300"
                            : "border-slate-800/80 bg-slate-900/40 text-slate-500 hover:text-slate-300"
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-semibold">
                          <span>{item.title}</span>
                          {done && <Check className="h-3.5 w-3.5 text-cyan-400" />}
                        </div>
                        <div className="mt-0.5 truncate text-[11px] text-slate-400">
                          {item.sub}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-5">
                {!config ? (
                  <div className="flex items-center justify-center py-12 text-xs text-slate-400">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading devices…
                  </div>
                ) : (
                  <>
                    {/* STEP 1: VISUAL PHONE PRESET CARDS */}
                    {wizardStep === 1 && (
                      <div className="space-y-4">
                        <div>
                          <h2 className="text-sm font-semibold text-white">
                            Choose Your Phone Model
                          </h2>
                          <p className="mt-0.5 text-xs text-slate-400">
                            Pre-calibrated case dimensions, tactile button pockets, and camera guard.
                          </p>
                        </div>

                        <div className="grid grid-cols-2 gap-2.5">
                          {presets.map((p) => {
                            const isSelected = config.id === p.id;
                            return (
                              <button
                                key={p.id}
                                type="button"
                                onClick={() => handleSelectPreset(p.id)}
                                className={`group flex flex-col justify-between rounded-xl border p-3.5 text-left transition-all ${
                                  isSelected
                                    ? "border-cyan-400 bg-cyan-500/10 ring-1 ring-cyan-400/25"
                                    : "border-slate-800 bg-slate-900/70 hover:border-slate-700 hover:bg-slate-800/40"
                                }`}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  {/* Mini phone silhouette icon */}
                                  <div
                                    className={`flex h-12 w-8 shrink-0 flex-col justify-between rounded-lg border-2 p-1 transition ${
                                      isSelected
                                        ? "border-cyan-400 bg-cyan-950/50"
                                        : "border-slate-700 bg-slate-950/70 group-hover:border-slate-500"
                                    }`}
                                  >
                                    <div
                                      className={`h-3 w-3 rounded-sm ${
                                        isSelected ? "bg-cyan-400/80" : "bg-slate-600"
                                      }`}
                                    />
                                    <div className="mx-auto h-0.5 w-3 rounded-full bg-slate-700" />
                                  </div>
                                  {isSelected && (
                                    <span className="rounded-full border border-cyan-400/30 bg-cyan-400/20 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">
                                      Active
                                    </span>
                                  )}
                                </div>

                                <div className="mt-3">
                                  <div className="text-xs font-semibold text-white group-hover:text-cyan-200 transition">
                                    {cleanDeviceName(p.name)}
                                  </div>
                                  <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                                    {p.body.length} × {p.body.width} × {p.body.thickness} mm
                                  </div>
                                </div>
                              </button>
                            );
                          })}
                        </div>

                        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/80 p-3.5">
                          <div>
                            <div className="text-xs font-medium text-slate-200">
                              Custom dimensions?
                            </div>
                            <div className="text-[11px] text-slate-400">
                              Measure with calipers & edit tolerances in Pro Mode.
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setUiMode("pro");
                              setProTab("calipers");
                            }}
                            className="shrink-0 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-cyan-300 hover:bg-slate-700"
                          >
                            Pro Calipers →
                          </button>
                        </div>
                      </div>
                    )}

                    {/* STEP 2: BACKPLATE DESIGN */}
                    {wizardStep === 2 && (
                      <div className="space-y-4">
                        <div>
                          <h2 className="text-sm font-semibold text-white">
                            Backplate Style & Finish
                          </h2>
                          <p className="mt-0.5 text-xs text-slate-400">
                            Customize the snap-in rigid backplate pattern or laser-cut outline.
                          </p>
                        </div>
                        {renderPatternControls()}
                      </div>
                    )}

                    {/* STEP 3: 1-CLICK MATERIAL THEMES & EXPORT */}
                    {wizardStep === 3 && (
                      <div className="space-y-5">
                        <div>
                          <h2 className="text-sm font-semibold text-white">
                            1-Click Filament Color Themes
                          </h2>
                          <p className="mt-0.5 text-xs text-slate-400">
                            Preview multi-material Bambu AMS color combos before exporting.
                          </p>
                        </div>

                        <div className="grid grid-cols-2 gap-2.5">
                          {FILAMENT_THEMES.map((theme) => {
                            const active = activeThemeId === theme.id;
                            return (
                              <button
                                key={theme.id}
                                type="button"
                                onClick={() => {
                                  setActiveThemeId(theme.id);
                                  setColors(theme.colors);
                                }}
                                className={`rounded-xl border p-3 text-left transition-all ${
                                  active
                                    ? "border-cyan-400 bg-cyan-500/10 ring-1 ring-cyan-400/25"
                                    : "border-slate-800 bg-slate-900/70 hover:border-slate-700"
                                }`}
                              >
                                <div className="mb-2 flex items-center gap-1.5">
                                  {[
                                    theme.colors.frame,
                                    theme.colors.backplate,
                                    theme.colors.inlay,
                                    theme.colors.camera_ring,
                                  ].map((hex, i) => (
                                    <span
                                      key={i}
                                      className="h-4 w-4 rounded-full border border-white/15"
                                      style={{ backgroundColor: hex }}
                                    />
                                  ))}
                                </div>
                                <div className="text-xs font-semibold text-white">
                                  {theme.name}
                                </div>
                                <div className="truncate text-[10px] text-slate-400">
                                  {theme.subtitle}
                                </div>
                              </button>
                            );
                          })}
                        </div>

                        {/* Individual Color Fine-Tuning */}
                        <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                          <div className="text-xs font-semibold text-slate-300">
                            Fine-Tune Part Colors
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            {[
                              { key: "frame", label: "Bumper (TPU)" },
                              { key: "backplate", label: "Backplate" },
                              { key: "inlay", label: "AMS Inlay" },
                              { key: "camera_ring", label: "Camera Ring" },
                              { key: "buttons", label: "Buttons" },
                            ].map((p) => (
                              <label
                                key={p.key}
                                className="flex cursor-pointer items-center justify-between rounded-lg border border-slate-800 bg-slate-950/70 px-2.5 py-1.5 hover:border-slate-700"
                              >
                                <span className="text-xs text-slate-300">
                                  {p.label}
                                </span>
                                <input
                                  type="color"
                                  value={colors[p.key]}
                                  onChange={(e) => {
                                    setActiveThemeId("custom");
                                    setColors((prev) => ({
                                      ...prev,
                                      [p.key]: e.target.value,
                                    }));
                                  }}
                                  className="h-5 w-6 cursor-pointer border-0 bg-transparent"
                                />
                              </label>
                            ))}
                          </div>
                        </div>

                        {/* Printer Calibration Presets */}
                        <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                          <div className="text-xs font-semibold text-slate-300">
                            Printer Calibration Profile
                          </div>
                          <div className="grid grid-cols-3 gap-1.5">
                            {CALIBRATION_PROFILES.map((cal) => {
                              const active = activeCalId === cal.id;
                              return (
                                <button
                                  key={cal.id}
                                  type="button"
                                  onClick={() => {
                                    setActiveCalId(cal.id);
                                    updateConfig((c) => {
                                      c.clearances = { ...c.clearances, ...cal.clearances };
                                      return c;
                                    }, true);
                                  }}
                                  className={`rounded-lg border px-2 py-2 text-left transition ${
                                    active
                                      ? "border-cyan-400 bg-cyan-500/15 text-cyan-200"
                                      : "border-slate-800 bg-slate-950/70 text-slate-400 hover:text-slate-200"
                                  }`}
                                >
                                  <div className="text-[11px] font-semibold leading-tight">
                                    {cal.label}
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                          <p className="text-[11px] text-slate-400">
                            {CALIBRATION_PROFILES.find((x) => x.id === activeCalId)?.desc}
                          </p>
                        </div>

                        {/* Tool-Changer & 1-Piece Export Card */}
                        <div className="space-y-2.5 rounded-xl border border-indigo-500/30 bg-gradient-to-br from-indigo-950/35 to-slate-900 p-3.5">
                          <div>
                            <div className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
                              Tool-Changer / Single-Piece Print
                            </div>
                            <p className="mt-0.5 text-[11px] text-slate-300">
                              Co-printed multi-toolhead assembly (H3C) or fused 1-piece TPU unibody.
                            </p>
                          </div>
                          <button
                            type="button"
                            disabled={exporting !== null}
                            onClick={() => handleExportPart("toolchanger_3mf", "Toolchanger_InPlace.3mf")}
                            className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-500 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-400 transition disabled:opacity-50"
                          >
                            <Download className="h-3.5 w-3.5" />
                            {exporting === "toolchanger_3mf"
                              ? "Packaging .3MF…"
                              : "Download H3C Tool-Changer In-Place (.3mf)"}
                          </button>
                          <button
                            type="button"
                            disabled={exporting !== null}
                            onClick={() => handleExportPart("unibody_stl", "Unibody_OnePiece.stl")}
                            className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-900/90 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 transition disabled:opacity-50"
                          >
                            <Download className="h-3.5 w-3.5 text-indigo-300" />
                            {exporting === "unibody_stl"
                              ? "Generating Unibody…"
                              : "Download 1-Piece Fused Unibody (.stl)"}
                          </button>
                        </div>

                        {/* 4-Part Modular Bundle Card */}
                        <div className="space-y-3 rounded-xl border border-cyan-500/30 bg-gradient-to-br from-cyan-950/40 to-slate-900 p-4">
                          <div>
                            <div className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
                              4-Part Modular Slicer Bundle
                            </div>
                            <p className="mt-1 text-xs text-slate-300">
                              Pre-oriented flat on Z=0, support-free, packaged as `.3mf`, `.stl`, `.step`, and laser `.svg`.
                            </p>
                          </div>

                          <button
                            type="button"
                            disabled={exporting !== null}
                            onClick={() => handleExportZip(false)}
                            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-500 px-4 py-2.5 text-xs font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 hover:bg-cyan-400 transition disabled:opacity-50"
                          >
                            <Download className="h-4 w-4" />
                            {exporting === "full"
                              ? "Packaging Bundle…"
                              : "Export Complete All-in-One Bundle (.zip)"}
                          </button>

                          <button
                            type="button"
                            disabled={exporting !== null}
                            onClick={() => handleExportZip(true)}
                            className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/90 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800 transition disabled:opacity-50"
                          >
                            <Download className="h-3.5 w-3.5 text-amber-400" />
                            {exporting === "coupon"
                              ? "Packaging Coupon…"
                              : "Download 10-Min Fit-Test Coupon (.zip)"}
                          </button>
                        </div>

                        {/* Quick Single-Part Re-Print Pills */}
                        <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                          <div className="text-xs font-semibold text-slate-300">
                            Quick Single-Part Re-Prints
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {[
                              { key: "backplate_3mf", label: "Backplate .3MF", file: "Backplate.3mf" },
                              { key: "frame_stl", label: "Frame .STL", file: "Frame_TPU.stl" },
                              { key: "buttons_stl", label: "Buttons .STL", file: "Buttons.stl" },
                              { key: "ring_stl", label: "Camera Ring .STL", file: "CameraRing.stl" },
                              { key: "laser_svg", label: "Laser .SVG", file: "Laser_Backplate.svg" },
                            ].map((item) => (
                              <button
                                key={item.key}
                                type="button"
                                disabled={exporting !== null}
                                onClick={() => handleExportPart(item.key, item.file)}
                                className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-[11px] font-medium text-slate-200 hover:border-cyan-500 transition disabled:opacity-50"
                              >
                                <Download className="h-3 w-3 text-cyan-400" />
                                {exporting === item.key ? "…" : item.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Wizard Footer Navigation */}
              <div className="flex items-center justify-between border-t border-slate-800/80 bg-slate-900/60 px-4 py-3">
                <button
                  type="button"
                  disabled={wizardStep === 1}
                  onClick={() => setWizardStep((s) => Math.max(1, s - 1))}
                  className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 disabled:opacity-40 transition"
                >
                  ← Back
                </button>
                <span className="text-xs text-slate-400">
                  Step <strong className="text-white">{wizardStep}</strong> of 3
                </span>
                {wizardStep < 3 ? (
                  <button
                    type="button"
                    onClick={() => setWizardStep((s) => Math.min(3, s + 1))}
                    className="rounded-lg bg-cyan-500 px-4 py-1.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400 transition"
                  >
                    Next →
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={exporting !== null}
                    onClick={() => handleExportZip(false)}
                    className="rounded-lg bg-emerald-400 px-4 py-1.5 text-xs font-semibold text-slate-950 hover:bg-emerald-300 transition disabled:opacity-50"
                  >
                    Download .ZIP
                  </button>
                )}
              </div>
            </>
          ) : (
            /* -------------------- PRO CAD MODE (ALL ENGINEERING CONTROLS) -------------------- */
            <>
              <div className="grid grid-cols-4 border-b border-slate-800 bg-slate-950/60 text-[11px] font-medium">
                {[
                  { id: "calipers", label: "Calipers", icon: Smartphone },
                  { id: "tolerances", label: "Tolerances", icon: Sliders },
                  { id: "pattern", label: "Pattern", icon: Sparkles },
                  { id: "colors", label: "Colors", icon: Palette },
                ].map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setProTab(id)}
                    className={`flex flex-col items-center gap-1 border-b-2 py-2.5 transition ${
                      proTab === id
                        ? "border-cyan-400 bg-slate-900/70 text-cyan-300"
                        : "border-transparent text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-5">
                {!config ? (
                  <div className="flex items-center justify-center py-12 text-xs text-slate-400">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading presets…
                  </div>
                ) : (
                  <>
                    {/* PRO TAB 1: CALIPERS */}
                    {proTab === "calipers" && (
                      <div className="space-y-5">
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                              Base Device Preset
                            </label>
                            <div className="flex items-center gap-1.5">
                              <label className="cursor-pointer rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300 hover:border-cyan-500">
                                Import JSON
                                <input
                                  type="file"
                                  accept=".json,application/json"
                                  onChange={handleImportPresetJson}
                                  className="hidden"
                                />
                              </label>
                              <button
                                type="button"
                                onClick={handleExportPresetJson}
                                className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-cyan-300 hover:border-cyan-500"
                              >
                                Export JSON
                              </button>
                            </div>
                          </div>
                          <select
                            value={config.id}
                            onChange={(e) => handleSelectPreset(e.target.value)}
                            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-100 outline-none focus:border-cyan-500"
                          >
                            {presets.map((p) => (
                              <option key={p.id} value={p.id}>
                                {cleanDeviceName(p.name)}
                              </option>
                            ))}
                          </select>
                        </div>

                        <section className="space-y-2.5">
                          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                            Body Caliper Dimensions
                          </h2>
                          <div className="grid grid-cols-2 gap-2.5">
                            <NumberField
                              label="Length (L)"
                              value={config.body.length}
                              min={80}
                              max={220}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.body.length = v;
                                  return c;
                                })
                              }
                            />
                            <NumberField
                              label="Width (W)"
                              value={config.body.width}
                              min={50}
                              max={120}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.body.width = v;
                                  return c;
                                })
                              }
                            />
                            <NumberField
                              label="Thickness (T)"
                              value={config.body.thickness}
                              min={4}
                              max={20}
                              step={0.05}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.body.thickness = v;
                                  return c;
                                })
                              }
                            />
                            <NumberField
                              label="Corner Radius (R)"
                              value={config.body.corner_radius}
                              min={0}
                              max={35}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.body.corner_radius = v;
                                  return c;
                                })
                              }
                            />
                          </div>
                        </section>

                        <section className="space-y-2.5">
                          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                            Camera Island (Back Top-Left Origin)
                          </h2>
                          <div className="grid grid-cols-3 gap-2">
                            <NumberField
                              label="X Offset"
                              value={config.camera.x}
                              min={0}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.camera.x = v;
                                  return c;
                                })
                              }
                            />
                            <NumberField
                              label="Y Offset"
                              value={config.camera.y}
                              min={0}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.camera.y = v;
                                  return c;
                                })
                              }
                            />
                            <NumberField
                              label="Radius"
                              value={config.camera.radius}
                              min={0}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.camera.radius = v;
                                  return c;
                                })
                              }
                            />
                          </div>
                          <div className="grid grid-cols-2 gap-2.5">
                            <NumberField
                              label="Camera Width"
                              value={config.camera.width}
                              min={5}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.camera.width = v;
                                  return c;
                                })
                              }
                            />
                            <NumberField
                              label="Camera Height"
                              value={config.camera.height}
                              min={5}
                              onChange={(v) =>
                                updateConfig((c) => {
                                  c.camera.height = v;
                                  return c;
                                })
                              }
                            />
                          </div>
                        </section>

                        {/* Floating Buttons */}
                        <section className="space-y-2">
                          <div className="flex items-center justify-between">
                            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                              Floating Buttons ({config.buttons.length})
                            </h2>
                            <button
                              type="button"
                              onClick={() =>
                                updateConfig((c) => {
                                  c.buttons.push({
                                    id: `btn_${c.buttons.length + 1}`,
                                    side: "right",
                                    pos: 65,
                                    length: 12,
                                  });
                                  return c;
                                }, true)
                              }
                              className="flex items-center gap-1 rounded border border-slate-700 px-2 py-0.5 text-[11px] text-cyan-300 hover:bg-slate-800"
                            >
                              <Plus className="h-3 w-3" /> Add Button
                            </button>
                          </div>
                          <div className="space-y-2">
                            {config.buttons.map((b, idx) => (
                              <div
                                key={`${b.id}-${idx}`}
                                className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5"
                              >
                                <div className="flex items-center gap-2">
                                  <input
                                    value={b.id}
                                    onChange={(e) =>
                                      updateConfig((c) => {
                                        c.buttons[idx].id = e.target.value;
                                        return c;
                                      })
                                    }
                                    className="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-100"
                                  />
                                  <select
                                    value={b.side}
                                    onChange={(e) =>
                                      updateConfig((c) => {
                                        c.buttons[idx].side = e.target.value;
                                        return c;
                                      }, true)
                                    }
                                    className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-200"
                                  >
                                    <option value="right">right</option>
                                    <option value="left">left</option>
                                    <option value="top">top</option>
                                    <option value="bottom">bottom</option>
                                  </select>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      updateConfig((c) => {
                                        c.buttons.splice(idx, 1);
                                        return c;
                                      }, true)
                                    }
                                    className="ml-auto text-slate-500 hover:text-rose-400"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                  <NumberField
                                    label="Pos from Top/Left"
                                    value={b.pos}
                                    step={0.5}
                                    onChange={(v) =>
                                      updateConfig((c) => {
                                        c.buttons[idx].pos = v;
                                        return c;
                                      })
                                    }
                                  />
                                  <NumberField
                                    label="Length"
                                    value={b.length}
                                    step={0.5}
                                    onChange={(v) =>
                                      updateConfig((c) => {
                                        c.buttons[idx].length = v;
                                        return c;
                                      })
                                    }
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </section>

                        {/* Ports */}
                        <section className="space-y-2">
                          <div className="flex items-center justify-between">
                            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                              Bottom / Side Ports ({config.ports.length})
                            </h2>
                            <button
                              type="button"
                              onClick={() =>
                                updateConfig((c) => {
                                  c.ports.push({
                                    id: `port_${c.ports.length + 1}`,
                                    side: "bottom",
                                    center: 0,
                                    width: 10,
                                    height: 5,
                                    radius: 2,
                                    z_offset: 0,
                                  });
                                  return c;
                                }, true)
                              }
                              className="flex items-center gap-1 rounded border border-slate-700 px-2 py-0.5 text-[11px] text-cyan-300 hover:bg-slate-800"
                            >
                              <Plus className="h-3 w-3" /> Add Port
                            </button>
                          </div>
                          <div className="space-y-2">
                            {config.ports.map((pt, idx) => (
                              <div
                                key={`${pt.id}-${idx}`}
                                className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5"
                              >
                                <div className="flex items-center gap-2">
                                  <input
                                    value={pt.id}
                                    onChange={(e) =>
                                      updateConfig((c) => {
                                        c.ports[idx].id = e.target.value;
                                        return c;
                                      })
                                    }
                                    className="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-100"
                                  />
                                  <select
                                    value={pt.side}
                                    onChange={(e) =>
                                      updateConfig((c) => {
                                        c.ports[idx].side = e.target.value;
                                        return c;
                                      }, true)
                                    }
                                    className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-200"
                                  >
                                    <option value="bottom">bottom</option>
                                    <option value="top">top</option>
                                    <option value="left">left</option>
                                    <option value="right">right</option>
                                  </select>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      updateConfig((c) => {
                                        c.ports.splice(idx, 1);
                                        return c;
                                      }, true)
                                    }
                                    className="ml-auto text-slate-500 hover:text-rose-400"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                                <div className="grid grid-cols-3 gap-2">
                                  <NumberField
                                    label="Center"
                                    value={pt.center}
                                    step={0.5}
                                    onChange={(v) =>
                                      updateConfig((c) => {
                                        c.ports[idx].center = v;
                                        return c;
                                      })
                                    }
                                  />
                                  <NumberField
                                    label="Width"
                                    value={pt.width}
                                    step={0.5}
                                    onChange={(v) =>
                                      updateConfig((c) => {
                                        c.ports[idx].width = v;
                                        return c;
                                      })
                                    }
                                  />
                                  <NumberField
                                    label="Height"
                                    value={pt.height}
                                    step={0.5}
                                    onChange={(v) =>
                                      updateConfig((c) => {
                                        c.ports[idx].height = v;
                                        return c;
                                      })
                                    }
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </section>
                      </div>
                    )}

                    {/* PRO TAB 2: TOLERANCES & CROSS-SECTION */}
                    {proTab === "tolerances" && (
                      <div className="space-y-5">
                        <CrossSectionDiagram
                          clearances={config.clearances}
                          style={config.style}
                        />

                        <section className="space-y-3">
                          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                            Print Clearances (FDM Fit)
                          </h2>
                          <SliderField
                            label="Frame-to-Phone Offset"
                            value={config.clearances.frame_to_phone_offset}
                            min={0.05}
                            max={0.6}
                            step={0.01}
                            hint="Radial air gap around phone perimeter"
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.clearances.frame_to_phone_offset = v;
                                return c;
                              })
                            }
                          />
                          <SliderField
                            label="Backplate Snap Clearance"
                            value={config.clearances.backplate_snap_clearance}
                            min={0.05}
                            max={0.35}
                            step={0.01}
                            hint="Tolerance between plate tongue and TPU groove"
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.clearances.backplate_snap_clearance = v;
                                return c;
                              })
                            }
                          />
                          <SliderField
                            label="Button Pocket Clearance"
                            value={config.clearances.button_clearance}
                            min={0.05}
                            max={0.45}
                            step={0.01}
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.clearances.button_clearance = v;
                                return c;
                              })
                            }
                          />
                          <SliderField
                            label="Camera Ring Press Clearance"
                            value={config.clearances.camera_ring_clearance}
                            min={0.05}
                            max={0.35}
                            step={0.01}
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.clearances.camera_ring_clearance = v;
                                return c;
                              })
                            }
                          />
                        </section>

                        <section className="space-y-3 border-t border-slate-800 pt-4">
                          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                            Wall & Snap-Lock Geometry
                          </h2>
                          <SliderField
                            label="TPU Frame Wall"
                            value={config.style.frame_wall}
                            min={1.4}
                            max={2.4}
                            step={0.05}
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.style.frame_wall = v;
                                return c;
                              })
                            }
                          />
                          <SliderField
                            label="Front Screen Lip"
                            value={config.style.front_lip}
                            min={0.6}
                            max={2.0}
                            step={0.05}
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.style.front_lip = v;
                                return c;
                              })
                            }
                          />
                          <SliderField
                            label="Backplate Thickness"
                            value={config.style.backplate_thickness}
                            min={1.6}
                            max={2.0}
                            step={0.05}
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.style.backplate_thickness = v;
                                return c;
                              })
                            }
                          />
                          <SliderField
                            label="Retention Groove Depth"
                            value={config.style.groove_depth}
                            min={0.6}
                            max={1.2}
                            step={0.05}
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.style.groove_depth = v;
                                return c;
                              })
                            }
                          />
                          <SliderField
                            label="Snap Lip Engagement"
                            value={config.style.snap_engage}
                            min={0.4}
                            max={0.85}
                            step={0.05}
                            onChange={(v) =>
                              updateConfig((c) => {
                                c.style.snap_engage = v;
                                return c;
                              })
                            }
                          />
                        </section>
                      </div>
                    )}

                    {/* PRO TAB 3: PATTERN */}
                    {proTab === "pattern" && renderPatternControls()}

                    {/* PRO TAB 4: COLORS */}
                    {proTab === "colors" && (
                      <div className="space-y-4">
                        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                          Filament & AMS Color Library
                        </h2>
                        {[
                          { key: "frame", label: "Frame (TPU 95A / 68D)" },
                          { key: "backplate", label: "Backplate Base (PLA / PETG / Wood)" },
                          { key: "inlay", label: "Backplate Inlay (AMS Slot 2)" },
                          { key: "camera_ring", label: "Camera Protection Ring" },
                          { key: "buttons", label: "Floating Tactile Buttons" },
                        ].map(({ key, label }) => (
                          <div
                            key={key}
                            className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-medium text-slate-200">
                                {label}
                              </span>
                              <input
                                type="color"
                                value={colors[key]}
                                onChange={(e) => {
                                  setActiveThemeId("custom");
                                  setColors((c) => ({ ...c, [key]: e.target.value }));
                                }}
                                className="h-6 w-8 cursor-pointer rounded border border-slate-700 bg-transparent"
                              />
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {BAMBU_SWATCHES.map((sw) => (
                                <button
                                  key={sw.hex}
                                  title={sw.name}
                                  type="button"
                                  onClick={() => {
                                    setActiveThemeId("custom");
                                    setColors((c) => ({ ...c, [key]: sw.hex }));
                                  }}
                                  style={{ backgroundColor: sw.hex }}
                                  className={`h-4 w-4 rounded-full border transition ${
                                    colors[key] === sw.hex
                                      ? "scale-110 border-white"
                                      : "border-slate-700 hover:scale-105"
                                  }`}
                                />
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </aside>

        {/* RIGHT PANE: FLOATING CANVAS HUD + VIEWPORT */}
        <main className="relative flex-1 overflow-hidden">
          {/* Unified Non-Overlapping Top HUD Row */}
          <div className="pointer-events-none absolute top-3 left-3 right-3 z-20 flex flex-wrap items-start justify-between gap-2">
            {/* Top-Left Summary / Bed Pill */}
            <div className="pointer-events-auto flex flex-wrap items-center gap-1.5">
              {viewMode === "bed" && (
                <span className="rounded-lg border border-cyan-500/40 bg-slate-900/85 px-2.5 py-1.5 text-xs font-medium text-cyan-300 shadow backdrop-blur-md">
                  Bambu 256×256 mm Build Plate (Z=0)
                </span>
              )}
              {preview?.summary && (
                <span className="rounded-lg border border-slate-800 bg-slate-900/85 px-2.5 py-1.5 text-xs text-slate-300 shadow backdrop-blur-md">
                  Outer: {preview.summary.outer_width} × {preview.summary.outer_length} × {preview.summary.total_height} mm
                </span>
              )}
            </div>

            {/* Top-Right Viewport Controls Bar */}
            <div className="pointer-events-auto flex flex-wrap items-center gap-2 rounded-xl border border-slate-800/90 bg-slate-900/85 p-1.5 shadow-xl backdrop-blur-md">
              <div className="flex items-center gap-0.5 rounded-lg bg-slate-950/80 p-0.5 text-xs">
                {[
                  { id: "assembly", label: "3D Assembly", icon: Layers },
                  { id: "bed", label: "Print Bed (Z=0)", icon: Grid3X3 },
                  { id: "svg", label: "2D Laser SVG", icon: FileCode2 },
                ].map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setViewMode(id)}
                    className={`flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1 font-medium transition ${
                      viewMode === id
                        ? "border border-cyan-500/30 bg-cyan-500/20 text-cyan-300"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </button>
                ))}
              </div>

              {viewMode === "assembly" && (
                <>
                  <div className="h-4 w-px bg-slate-800" />
                  <div className="flex items-center gap-2 px-1.5">
                    <span className="text-[11px] font-medium text-slate-400">
                      Explode
                    </span>
                    <input
                      aria-label="Exploded View"
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={explode}
                      onChange={(e) => setExplode(parseFloat(e.target.value))}
                      className="h-1.5 w-20 cursor-pointer accent-cyan-400"
                    />
                    <span className="w-8 text-right font-mono text-[11px] text-cyan-300">
                      {Math.round(explode * 100)}%
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowPhoneGhost((v) => !v)}
                    className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
                      showPhoneGhost
                        ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-300"
                        : "border-slate-700 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Phone Ghost
                  </button>
                </>
              )}

              {loading && (
                <div className="flex items-center gap-1.5 rounded-lg bg-cyan-500/15 px-2.5 py-1 text-[11px] font-medium text-cyan-300">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  OCCT
                </div>
              )}
            </div>
          </div>

          {/* Error Toast Banner */}
          {error && (
            <div className="absolute top-20 right-3 z-20 max-w-md rounded-xl border border-rose-500/40 bg-rose-950/90 px-3.5 py-2 text-xs text-rose-200 shadow-xl backdrop-blur">
              <strong className="font-semibold">Validation / CAD Error: </strong>
              {error}
            </div>
          )}

          {viewMode === "svg" ? (
            <div className="flex h-full w-full flex-col items-center justify-center bg-slate-950 p-8 pt-20">
              <div className="mb-4 flex w-full max-w-xl items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-200">
                    Laser-Cut Backplate Profile (Laser_Backplate.svg)
                  </h2>
                  <p className="text-xs text-slate-400">
                    1:1 mm closed paths · Rear View · Ready for Glowforge / LightBurn
                  </p>
                </div>
                <button
                  type="button"
                  disabled={!preview?.laser_svg}
                  onClick={handleDownloadLaserSvg}
                  className="flex items-center gap-1.5 rounded-lg bg-rose-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-400 disabled:opacity-50"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download .SVG
                </button>
              </div>
              <div className="flex max-h-[70vh] w-full max-w-xl items-center justify-center rounded-xl border border-slate-800 bg-white p-6 shadow-2xl">
                {preview?.laser_svg ? (
                  <div
                    className="flex max-h-[60vh] w-full justify-center [&>svg]:max-h-[60vh] [&>svg]:w-auto"
                    dangerouslySetInnerHTML={{ __html: preview.laser_svg }}
                  />
                ) : (
                  <span className="text-xs text-slate-500">Generating SVG…</span>
                )}
              </div>
            </div>
          ) : (
            <>
              <Viewport3D
                preview={preview}
                viewMode={viewMode}
                explode={explode}
                colors={colors}
                visibleGroups={visibleGroups}
                showPhoneGhost={showPhoneGhost}
                hideHud
              />

              {/* Unified Non-Overlapping Bottom HUD Stack */}
              <div className="pointer-events-none absolute bottom-3 left-3 right-3 z-10 flex flex-col gap-2">
                {/* Row 1: Part Visibility Pills */}
                <div className="pointer-events-auto flex flex-wrap items-center gap-1.5 self-start rounded-xl border border-slate-800/90 bg-slate-900/85 px-2.5 py-1.5 shadow-lg backdrop-blur-md">
                  <span className="mr-0.5 text-[11px] font-medium text-slate-400">
                    Parts:
                  </span>
                  {[
                    { key: "frame", label: "Frame" },
                    { key: "backplate", label: "Backplate" },
                    ...(hasInlay ? [{ key: "inlay", label: "Inlay" }] : []),
                    { key: "camera_ring", label: "Camera Ring" },
                    { key: "buttons", label: "Buttons" },
                  ].map((part) => {
                    const visible = visibleGroups[part.key] !== false;
                    return (
                      <button
                        key={part.key}
                        type="button"
                        onClick={() =>
                          setVisibleGroups((v) => ({
                            ...v,
                            [part.key]: !visible,
                          }))
                        }
                        className={`flex items-center gap-1.5 rounded-lg border px-2 py-0.5 text-[11px] font-medium transition ${
                          visible
                            ? "border-slate-700 bg-slate-800/90 text-slate-200"
                            : "border-slate-800/60 bg-slate-950/60 text-slate-500 line-through"
                        }`}
                      >
                        <span
                          className="h-2.5 w-2.5 rounded-full border border-white/15"
                          style={{ backgroundColor: colors[part.key] }}
                        />
                        {part.label}
                      </button>
                    );
                  })}
                </div>

                {/* Row 2: Camera Hint & OCCT Timings */}
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                  <span className="rounded-lg border border-slate-800/80 bg-slate-950/80 px-2.5 py-1 backdrop-blur">
                    Drag: Orbit · Right-Drag: Pan · Scroll: Zoom
                  </span>
                  {preview?.timings && (
                    <span className="rounded-lg border border-slate-800/80 bg-slate-950/80 px-2.5 py-1 font-mono text-[10px] text-cyan-400/90 backdrop-blur">
                      OCCT B-Rep: frame {preview.timings.frame}s · plate {preview.timings.backplate}s · ring {preview.timings.camera_ring}s · btns {preview.timings.buttons}s
                    </span>
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
