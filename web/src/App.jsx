import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Wand2,
} from "lucide-react";
import Viewport3D from "./components/Viewport3D.jsx";
import CrossSectionDiagram from "./components/CrossSectionDiagram.jsx";
import PatternControls from "./components/PatternControls.jsx";
import ValidationStatus, { validationState } from "./components/ValidationStatus.jsx";
import DeviceBadge from "./components/DeviceBadge.jsx";
import PrinterSelect from "./components/PrinterSelect.jsx";
import { NumberField, SliderField } from "./components/Fields.jsx";
import {
  BAMBU_SWATCHES,
  CALIBRATION_PROFILES,
  DEFAULT_VISIBLE,
  FILAMENT_THEMES,
  cleanDeviceName,
} from "./constants.jsx";
import usePreview from "./hooks/usePreview.js";
import useExports from "./hooks/useExports.js";
import useProject from "./hooks/useProject.js";
import FileMenu from "./components/FileMenu.jsx";
import FilePickButton from "./components/FilePickButton.jsx";
import { apiFetch, downloadBlob, postJson } from "./api.js";
import { IS_DESKTOP, call, confirmAction, saveTextFile } from "./desktop.js";

const COUPON_TYPES = [
  { id: "camera", label: "Camera & Snap", desc: "Camera ring, backplate snap joint and nearest button" },
  { id: "buttons", label: "Buttons", desc: "Real button pockets, buttons and the wall around them" },
  { id: "ports", label: "Bottom Ports", desc: "Charging & speaker openings in the bottom wall" },
];

export default function App() {
  const [presets, setPresets] = useState([]);
  const [printers, setPrinters] = useState([]);
  const [printerId, setPrinterId] = useState("generic_256");
  const [config, setConfig] = useState(null);

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
  const [couponType, setCouponType] = useState("camera");

  // Request status: preview requests live in usePreview; this is for load/export/import errors
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null); // {text, path?} -- success toast
  const [userPresetIds, setUserPresetIds] = useState([]);
  const [deviceName, setDeviceName] = useState(null); // "Save as my device" inline form (null = closed)
  const defaultsRef = useRef({ presetId: null, printerId: "generic_256" });
  const delayRef = useRef(0); // debounce for the NEXT preview request (ms)

  const { preview, status, error: previewError, invalid, isCurrent, refresh } = usePreview(
    config,
    printerId,
    delayRef
  );
  const findings = isCurrent ? preview?.findings : null;
  const vState = validationState({ status, error: previewError, invalid, findings });
  const canExport = Boolean(config && isCurrent && !preview?.export_blocked);
  const exportBlockedReason = !canExport
    ? status === "loading"
      ? "Waiting for the preview of the current design"
      : "Fix the findings shown in the validation status first"
    : undefined;
  const { exporting, exportZip, exportPart } = useExports({
    config,
    printerId,
    canExport,
    onError: setError,
    onSaved: (r) => setNotice({ text: `Saved ${r.name}`, path: r.path }),
  });
  const printer = useMemo(() => printers.find((p) => p.id === printerId), [printers, printerId]);
  const loading = status === "loading";
  const dirty = !isCurrent;

  const loadPresets = useCallback(async () => {
    const data = await (await apiFetch("/api/presets")).json();
    setPresets(data.presets);
    setUserPresetIds(data.user_ids || []);
    if (data.skipped?.length) {
      setError(
        `Skipped ${data.skipped.length} damaged device file(s): ` +
          data.skipped.map((s) => `${s.file} (${s.error})`).join("; ")
      );
    }
    return data;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [data, pdata] = await Promise.all([
          loadPresets(),
          apiFetch("/api/printers")
            .then((r) => r.json())
            .catch(() => null),
        ]);
        if (pdata) {
          setPrinters(pdata.printers);
          setPrinterId(pdata.default_id);
          defaultsRef.current.printerId = pdata.default_id;
        }
        defaultsRef.current.presetId = data.default_id;
        const initial = data.presets.find((p) => p.id === data.default_id) || data.presets[0];
        if (initial) {
          delayRef.current = 0;
          setConfig(structuredClone(initial));
        } else {
          setError("No device presets could be loaded. Reinstall CaseCraft Studio.");
        }
      } catch (err) {
        setError(`Could not load devices: ${err.message}`);
      }
    })();
  }, [loadPresets]);

  // auto-dismiss the success toast
  useEffect(() => {
    if (!notice) return undefined;
    const t = setTimeout(() => setNotice(null), 8000);
    return () => clearTimeout(t);
  }, [notice]);

  const updateConfig = useCallback((updater, immediate = false) => {
    setConfig((prev) => {
      if (!prev) return prev;
      delayRef.current = immediate ? 30 : 450;
      return typeof updater === "function" ? updater(structuredClone(prev)) : updater;
    });
  }, []);

  const replaceConfig = (next) => {
    delayRef.current = 0;
    setError(null);
    setConfig(next);
  };

  const handleSelectPrinter = (id) => {
    delayRef.current = 0;
    setPrinterId(id);
  };

  const handleSelectPreset = (id) => {
    const found = presets.find((p) => p.id === id);
    if (!found) return;
    const next = structuredClone(found);
    if (config?.pattern) next.pattern = structuredClone(config.pattern);
    replaceConfig(next);
  };

  const saveText = async (name, text, mime) => {
    const r = await saveTextFile(name, text, mime, downloadBlob);
    if (r.ok && r.path) setNotice({ text: `Saved ${r.name}`, path: r.path });
    else if (!r.ok && !r.cancelled) setError(r.error);
  };

  const handleExportPresetJson = () => {
    if (!config) return;
    saveText(`${config.id}_preset.json`, JSON.stringify(config, null, 2), "application/json");
  };

  const handleImportPresetJson = (text, fileName) => {
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      setError(`${fileName} is not valid JSON.`);
      return;
    }
    if (data?.format === "casecraft-project") {
      setError(`${fileName} is a project file; open it from the file menu instead.`);
      return;
    }
    if (!data || typeof data !== "object" || !data.body || !data.id) {
      setError(`${fileName} is not a CaseCraft device preset.`);
      return;
    }
    replaceConfig(data); // the preview validates it and reports any problems as findings
  };

  // ---- user device library ("My devices")
  const handleSaveDevice = async () => {
    const name = (deviceName || "").trim();
    if (!config || !name) return;
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60);
    const id = `my_${slug || "device"}`;
    if (userPresetIds.includes(id) && !(await confirmAction(`Replace your saved device "${name}"?`))) return;
    try {
      const res = await postJson("/api/user-presets", { ...config, id, name });
      const saved = await res.json();
      await loadPresets();
      setDeviceName(null);
      replaceConfig(saved.preset);
      setNotice({ text: `Saved "${name}" to My devices` });
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteDevice = async () => {
    if (!config || !userPresetIds.includes(config.id)) return;
    if (!(await confirmAction(`Delete "${config.name}" from My devices? The current design stays open.`))) return;
    try {
      await apiFetch(`/api/user-presets/${encodeURIComponent(config.id)}`, { method: "DELETE" });
      await loadPresets();
      setNotice({ text: `Deleted "${config.name}"` });
    } catch (err) {
      setError(err.message);
    }
  };

  // ---- projects (desktop)
  const applyProject = useCallback(
    (data) => {
      replaceConfig(structuredClone(data.config));
      if (data.printerId) {
        if (printers.some((p) => p.id === data.printerId)) setPrinterId(data.printerId);
        else setError(`Printer profile "${data.printerId}" is not available; using ${printerId}.`);
      }
      if (typeof data.themeId === "string") setActiveThemeId(data.themeId);
      if (data.colors && typeof data.colors === "object") setColors((c) => ({ ...c, ...data.colors }));
      if (COUPON_TYPES.some((c) => c.id === data.couponType)) setCouponType(data.couponType);
      if (typeof data.calId === "string") setActiveCalId(data.calId);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [printers, printerId]
  );

  const resetDesign = () => {
    const initial = presets.find((p) => p.id === defaultsRef.current.presetId) || presets[0];
    if (initial) replaceConfig(structuredClone(initial));
    setPrinterId(defaultsRef.current.printerId);
    setActiveThemeId(FILAMENT_THEMES[0].id);
    setColors(FILAMENT_THEMES[0].colors);
    setCouponType("camera");
    setActiveCalId("h3c");
  };

  const project = useProject({
    fields: { config, printerId, themeId: activeThemeId, colors, couponType, calId: activeCalId },
    ready: Boolean(config && presets.length),
    applyProject,
    resetDesign,
    onError: setError,
    onNotice: setNotice,
  });

  const handleExportZip = (coupon = false) => exportZip(coupon, couponType);
  const handleExportPart = exportPart;

  const handleDownloadLaserSvg = () => {
    if (!preview?.laser_svg || !config || !isCurrent) return;
    saveText(`${config.id}_Laser_Backplate.svg`, preview.laser_svg, "image/svg+xml");
  };

  const setCameraOpening = (key, value) =>
    updateConfig((c) => {
      c.camera.opening = { width: 0, height: 0, radius: 0, dx: 0, dy: 0, ...(c.camera.opening || {}), [key]: value };
      return c;
    });

  const hasInlay = Boolean(
    preview?.summary?.has_inlay ||
      preview?.parts?.some((p) => p.group === "inlay")
  );

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-950 text-slate-100 select-none">
      {/* ==================== CLEAN SINGLE-ROW HEADER ==================== */}
      <header className="z-30 flex min-h-14 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 bg-slate-900/85 px-4 py-2 backdrop-blur-md">
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
              {config && <DeviceBadge verification={config.verification} />}
              <FileMenu project={project} onNotice={setNotice} onError={setError} />
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
            onClick={refresh}
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

          <PrinterSelect printers={printers} value={printerId} onChange={handleSelectPrinter} />
          <ValidationStatus state={vState} />

          <button
            type="button"
            disabled={!canExport || exporting !== null}
            title={exportBlockedReason || COUPON_TYPES.find((c) => c.id === couponType)?.desc}
            onClick={() => handleExportZip(true)}
            className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-700 bg-slate-800/90 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700/80 disabled:opacity-50 transition"
          >
            {exporting === "coupon" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5 text-amber-400" />
            )}
            Fit Coupon
          </button>

          <button
            type="button"
            disabled={!canExport || exporting !== null}
            title={exportBlockedReason}
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
                                  <DeviceBadge verification={p.verification} className="mt-1.5 inline-block" />
                                  {userPresetIds.includes(p.id) && (
                                    <span className="ml-1.5 mt-1.5 inline-block rounded-full border border-violet-400/30 bg-violet-400/10 px-1.5 py-0.5 text-[10px] font-medium text-violet-300">
                                      My device
                                    </span>
                                  )}
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
                        {<PatternControls config={config} updateConfig={updateConfig} uiMode={uiMode} onError={setError} />}
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

                        {/* Printer profile (drives plate size, layout and print modes) */}
                        <div className="flex items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5">
                          <div>
                            <div className="text-xs font-semibold text-slate-300">Printer</div>
                            <div className="text-[11px] text-slate-400">
                              {printer ? `${printer.bed_x} × ${printer.bed_y} mm plate${printer.toolchanger ? " · toolchanger" : ""}` : "…"}
                            </div>
                          </div>
                          <PrinterSelect printers={printers} value={printerId} onChange={handleSelectPrinter} />
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
                            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-indigo-300">
                              Tool-Changer / Single-Piece Print
                              <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-semibold normal-case tracking-normal text-amber-300">
                                Print-in-place: experimental
                              </span>
                            </div>
                            <p className="mt-0.5 text-[11px] text-slate-300">
                              Co-printed multi-toolhead assembly (toolchanger printers only) or a 1-piece TPU unibody.
                            </p>
                            {!printer?.toolchanger && (
                              <p className="mt-1 text-[11px] text-amber-300/90">
                                Select a toolchanger printer profile (Bambu Lab H3C) to enable the co-printed export.
                              </p>
                            )}
                          </div>
                          <button
                            type="button"
                            disabled={!canExport || exporting !== null}
                            title={exportBlockedReason}
                            onClick={() => handleExportPart("toolchanger_3mf", "Toolchanger_InPlace.3mf")}
                            hidden={!printer?.toolchanger}
                            className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-500 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-400 transition disabled:opacity-50"
                          >
                            <Download className="h-3.5 w-3.5" />
                            {exporting === "toolchanger_3mf"
                              ? "Packaging .3MF…"
                              : "Download H3C Tool-Changer In-Place (.3mf)"}
                          </button>
                          <button
                            type="button"
                            disabled={!canExport || exporting !== null}
                            title={exportBlockedReason}
                            onClick={() => handleExportPart("unibody_stl", "Unibody_OnePiece.stl")}
                            className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-900/90 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 transition disabled:opacity-50"
                          >
                            <Download className="h-3.5 w-3.5 text-indigo-300" />
                            {exporting === "unibody_stl"
                              ? "Generating Unibody…"
                              : "Download 1-Piece Unibody (.stl)"}
                          </button>
                          {isCurrent && preview?.unibody_notes?.length > 0 && (
                            <ul className="list-disc space-y-0.5 pl-4 text-[10px] leading-snug text-slate-400">
                              {preview.unibody_notes.map((n) => (
                                <li key={n}>{n.replace(/^Unibody: /, "")}</li>
                              ))}
                            </ul>
                          )}
                        </div>

                        {/* 4-Part Modular Bundle Card */}
                        <div className="space-y-3 rounded-xl border border-cyan-500/30 bg-gradient-to-br from-cyan-950/40 to-slate-900 p-4">
                          <div>
                            <div className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
                              4-Part Modular Slicer Bundle
                            </div>
                            <p className="mt-1 text-xs text-slate-300">
                              Pre-oriented flat on Z=0, laid out for {printer?.name || "the selected printer"}, packaged as `.3mf`, `.stl`, `.step`, and laser `.svg`.
                            </p>
                            <div className="mt-2">
                              <ValidationStatus state={vState} align="left" />
                            </div>
                          </div>

                          <button
                            type="button"
                            disabled={!canExport || exporting !== null}
                            title={exportBlockedReason}
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
                            disabled={!canExport || exporting !== null}
                            title={exportBlockedReason}
                            onClick={() => handleExportZip(true)}
                            className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900/90 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800 transition disabled:opacity-50"
                          >
                            <Download className="h-3.5 w-3.5 text-amber-400" />
                            {exporting === "coupon"
                              ? "Packaging Coupon…"
                              : `Download ${COUPON_TYPES.find((c) => c.id === couponType)?.label} Fit-Test Coupon (.zip)`}
                          </button>
                          <div className="grid grid-cols-3 gap-1.5">
                            {COUPON_TYPES.map((ct) => (
                              <button
                                key={ct.id}
                                type="button"
                                title={ct.desc}
                                onClick={() => setCouponType(ct.id)}
                                className={`rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
                                  couponType === ct.id
                                    ? "border-amber-400/60 bg-amber-500/10 text-amber-200"
                                    : "border-slate-800 bg-slate-950/70 text-slate-400 hover:text-slate-200"
                                }`}
                              >
                                {ct.label}
                              </button>
                            ))}
                          </div>
                          <p className="text-[10px] text-slate-500">
                            {COUPON_TYPES.find((c) => c.id === couponType)?.desc}. Print it before a full case; slice it to see the print time.
                          </p>
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
                                disabled={!canExport || exporting !== null}
                            title={exportBlockedReason}
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
                    disabled={!canExport || exporting !== null}
                            title={exportBlockedReason}
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
                              <FilePickButton
                                accept=".json,application/json"
                                extensions={[".json"]}
                                onText={handleImportPresetJson}
                                onError={setError}
                                className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300 hover:border-cyan-500"
                              >
                                Import JSON
                              </FilePickButton>
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
                            {!presets.some((p) => p.id === config.id) && (
                              <option value={config.id}>{cleanDeviceName(config.name)} (unsaved)</option>
                            )}
                            <optgroup label="Built-in devices">
                              {presets
                                .filter((p) => !userPresetIds.includes(p.id))
                                .map((p) => (
                                  <option key={p.id} value={p.id}>
                                    {cleanDeviceName(p.name)}
                                  </option>
                                ))}
                            </optgroup>
                            {userPresetIds.length > 0 && (
                              <optgroup label="My devices">
                                {presets
                                  .filter((p) => userPresetIds.includes(p.id))
                                  .map((p) => (
                                    <option key={p.id} value={p.id}>
                                      {p.name}
                                    </option>
                                  ))}
                              </optgroup>
                            )}
                          </select>
                          {deviceName === null ? (
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() =>
                                  setDeviceName(
                                    userPresetIds.includes(config.id) ? config.name : `My ${cleanDeviceName(config.name)}`
                                  )
                                }
                                className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-violet-300 hover:border-violet-400"
                              >
                                Save as my device…
                              </button>
                              {userPresetIds.includes(config.id) && (
                                <button
                                  type="button"
                                  onClick={handleDeleteDevice}
                                  className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-rose-300 hover:border-rose-400"
                                >
                                  Delete my device
                                </button>
                              )}
                            </div>
                          ) : (
                            <form
                              className="flex items-center gap-1.5"
                              onSubmit={(e) => {
                                e.preventDefault();
                                handleSaveDevice();
                              }}
                            >
                              <input
                                autoFocus
                                value={deviceName}
                                maxLength={80}
                                onChange={(e) => setDeviceName(e.target.value)}
                                onKeyDown={(e) => e.key === "Escape" && setDeviceName(null)}
                                placeholder="Device name"
                                className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-100 outline-none focus:border-violet-400"
                              />
                              <button
                                type="submit"
                                disabled={!deviceName.trim()}
                                className="rounded bg-violet-500 px-2 py-1 text-[11px] font-semibold text-white disabled:opacity-50"
                              >
                                Save
                              </button>
                              <button
                                type="button"
                                onClick={() => setDeviceName(null)}
                                className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300"
                              >
                                Cancel
                              </button>
                            </form>
                          )}
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
                          <label className="flex cursor-pointer items-center gap-2 text-[11px] text-slate-300">
                            <input
                              type="checkbox"
                              checked={Boolean(config.camera.opening)}
                              onChange={(e) =>
                                updateConfig((c) => {
                                  c.camera.opening = e.target.checked
                                    ? { width: c.camera.width, height: c.camera.height, radius: c.camera.radius, dx: 0, dy: 0 }
                                    : null;
                                  return c;
                                }, true)
                              }
                              className="accent-cyan-400"
                            />
                            Separate outer-opening profile (island wider at its base, or flared opening)
                          </label>
                          {config.camera.opening && (
                            <div className="grid grid-cols-3 gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-2">
                              {[
                                ["width", "Opening W"],
                                ["height", "Opening H"],
                                ["radius", "Opening R"],
                                ["dx", "Shift X"],
                                ["dy", "Shift Y"],
                              ].map(([k, label]) => (
                                <NumberField
                                  key={k}
                                  label={label}
                                  value={config.camera.opening[k]}
                                  onChange={(v) => setCameraOpening(k, v)}
                                />
                              ))}
                              <p className="col-span-3 text-[10px] text-slate-500">
                                Width/Height above = island at its base; this is the clear opening at the outer face. Shift is measured on the back view (+X right, +Y down).
                              </p>
                            </div>
                          )}
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
                    {proTab === "pattern" && <PatternControls config={config} updateConfig={updateConfig} uiMode={uiMode} onError={setError} />}

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
                <span
                  className={`rounded-lg border bg-slate-900/85 px-2.5 py-1.5 text-xs font-medium shadow backdrop-blur-md ${
                    preview?.bed?.fits === false ? "border-rose-500/60 text-rose-300" : "border-cyan-500/40 text-cyan-300"
                  }`}
                >
                  {preview?.printer?.name || "Build plate"} · {preview?.bed?.x ?? 256}×{preview?.bed?.y ?? 256} mm
                  {preview?.bed?.fits === false ? " · parts do not fit" : " · Case_Set.3mf layout"}
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
          <div className="absolute top-20 right-3 z-20 flex max-w-md flex-col items-end gap-2">
            {project.restoreOffer && (
              <div className="rounded-xl border border-amber-500/40 bg-amber-950/90 px-3.5 py-2.5 text-xs text-amber-100 shadow-xl backdrop-blur">
                <div className="font-semibold">Restore your unsaved design?</div>
                <div className="mt-0.5 text-amber-200/80">
                  CaseCraft Studio closed before it was saved
                  {project.restoreOffer.savedAt ? ` (autosaved ${project.restoreOffer.savedAt.replace("T", " ")})` : ""}.
                </div>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={project.restore}
                    className="rounded-lg bg-amber-400 px-2.5 py-1 font-semibold text-slate-950 hover:bg-amber-300"
                  >
                    Restore
                  </button>
                  <button
                    type="button"
                    onClick={project.discardRestore}
                    className="rounded-lg border border-amber-500/40 px-2.5 py-1 text-amber-200 hover:bg-amber-500/10"
                  >
                    Discard
                  </button>
                </div>
              </div>
            )}
            {(error || previewError) && (
              <div className="flex items-start gap-2 rounded-xl border border-rose-500/40 bg-rose-950/90 px-3.5 py-2 text-xs text-rose-200 shadow-xl backdrop-blur">
                <div className="min-w-0 break-words">
                  <strong className="font-semibold">{error ? "Error: " : "Validation / CAD Error: "}</strong>
                  {error || previewError}
                </div>
                {error && (
                  <button
                    type="button"
                    aria-label="Dismiss"
                    onClick={() => setError(null)}
                    className="-mr-1 shrink-0 rounded px-1 text-rose-300 hover:bg-rose-500/20"
                  >
                    ×
                  </button>
                )}
              </div>
            )}
            {notice && (
              <div className="flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-950/90 px-3.5 py-2 text-xs text-emerald-100 shadow-xl backdrop-blur">
                <span className="min-w-0 break-words">{notice.text}</span>
                {notice.path && IS_DESKTOP && (
                  <button
                    type="button"
                    onClick={() => call("reveal", notice.path)}
                    className="shrink-0 rounded-lg border border-emerald-500/40 px-2 py-0.5 text-emerald-200 hover:bg-emerald-500/10"
                  >
                    Show in folder
                  </button>
                )}
                <button
                  type="button"
                  aria-label="Dismiss"
                  onClick={() => setNotice(null)}
                  className="shrink-0 rounded px-1 text-emerald-300 hover:bg-emerald-500/20"
                >
                  ×
                </button>
              </div>
            )}
          </div>

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
                  disabled={!preview?.laser_svg || !isCurrent}
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
                bed={preview?.bed}
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
