import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Check, Download, Loader2, Palette, Sliders, Smartphone, Sparkles, Wand2 } from "lucide-react";
import CrossSectionDiagram from "./components/CrossSectionDiagram.jsx";
import DeviceEditor from "./components/DeviceEditor.jsx";
import DevicePicker, { deviceBrand } from "./components/DevicePicker.jsx";
import PatternControls from "./components/PatternControls.jsx";
import PatternPreviewCard from "./components/PatternPreviewCard.jsx";
import ViewportToolbar from "./components/ViewportToolbar.jsx";
import usePatternSpecs from "./hooks/usePatternSpecs.js";
import usePatternRequest from "./hooks/usePatternRequest.js";
import ValidationStatus, { validationState } from "./components/ValidationStatus.jsx";
import DeviceBadge from "./components/DeviceBadge.jsx";
import PrinterSelect from "./components/PrinterSelect.jsx";
import { SliderField } from "./components/Fields.jsx";
import { fitLimits } from "./fitLimits.js";
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
import { apiFetch, downloadBlob, postJson } from "./api.js";
import { IS_DESKTOP, call, confirmAction, saveTextFile } from "./desktop.js";

// three.js and the 3D viewer load in their own chunk, after the panel is on screen
const Viewport3D = lazy(() => import("./components/Viewport3D.jsx"));

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

  // ---- pattern panel: live 2D back view + thumbnail gallery (fast endpoints, no CAD wait)
  const patternPanelOpen =
    Boolean(config) && ((uiMode === "simple" && wizardStep === 2) || (uiMode === "pro" && proTab === "pattern"));
  const { specs: patternSpecs, error: patternSpecsError, retry: retryPatternSpecs } = usePatternSpecs();
  const patternPreview = usePatternRequest("/api/pattern-preview", config, { enabled: patternPanelOpen });
  // thumbnails use each type's defaults, so only the settings they share change them
  const galleryBody = useMemo(
    () => config && { ...config, pattern: { ...config.pattern, type: "solid", params: {} } },
    [config]
  );
  const patternGallery = usePatternRequest("/api/pattern-gallery", galleryBody, {
    enabled: patternPanelOpen,
    delay: 250,
  });
  const patternTypeLabel = patternSpecs?.types?.find((t) => t.id === config?.pattern?.type)?.label;

  // ---- camera: frame the side that matters for the current step (the back while styling)
  const [viewRequest, setViewRequest] = useState(null);
  const requestView = useCallback((name) => setViewRequest((r) => ({ name, nonce: (r?.nonce || 0) + 1 })), []);
  const preferredView = patternPanelOpen ? "back" : "iso";
  useEffect(() => {
    if (viewMode === "assembly") requestView(preferredView);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferredView]);
  const handleViewMode = (mode) => {
    setViewMode(mode);
    if (mode === "bed") requestView("bed");
    else if (mode === "assembly") requestView(preferredView);
  };

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

  const hasInlay = Boolean(
    preview?.summary?.has_inlay ||
      preview?.parts?.some((p) => p.group === "inlay")
  );
  // slider ranges the engine accepts together with the rest of the design (params.py rules)
  const limits = useMemo(() => (config ? fitLimits(config) : null), [config]);
  // devices with an open camera cut-out (iPhone 17 family, camera plateaus) have no ring part:
  // exports follow the config, the viewport's part pills follow the model on screen
  const hasRing = config?.camera?.ring !== false;
  const shownRing = preview ? preview.summary?.has_camera_ring !== false : hasRing;
  // parameter warnings for the device editor; the last preview's are fine while a new one builds
  const deviceWarnings = useMemo(
    () =>
      (preview?.findings || [])
        .filter((f) => f.level === "warning" && f.source === "parameters")
        .map((f) => f.message),
    [preview]
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

        {/* Right: printer, validation and the primary export actions */}
        <div className="flex shrink-0 items-center gap-2">
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
                          <h2 className="text-sm font-semibold text-white">Choose your phone</h2>
                          <p className="mt-0.5 text-xs text-slate-400">
                            Pick the maker, then the model: case dimensions, button pockets and camera opening come with it.
                          </p>
                        </div>

                        <DevicePicker
                          presets={presets}
                          userPresetIds={userPresetIds}
                          activeId={config.id}
                          activeBrand={deviceBrand(config, userPresetIds)}
                          onSelect={handleSelectPreset}
                        />

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
                        <PatternPreviewCard request={patternPreview} colors={colors} typeLabel={patternTypeLabel} />
                        <PatternControls
                          config={config}
                          updateConfig={updateConfig}
                          uiMode={uiMode}
                          onError={setError}
                          specs={patternSpecs}
                          specsError={patternSpecsError}
                          onRetrySpecs={retryPatternSpecs}
                          gallery={patternGallery.data}
                          colors={colors}
                        />
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
                              ...(hasRing ? [{ key: "camera_ring", label: "Camera Ring" }] : []),
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
                              ...(hasRing ? [{ key: "ring_stl", label: "Camera Ring .STL", file: "CameraRing.stl" }] : []),
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
                  { id: "calipers", label: "Device", icon: Smartphone },
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
                    {/* PRO TAB 1: DEVICE (the phone itself, edited against a live sketch) */}
                    {proTab === "calipers" && (
                      <DeviceEditor
                        config={config}
                        presets={presets}
                        userPresetIds={userPresetIds}
                        updateConfig={updateConfig}
                        onSelectPreset={handleSelectPreset}
                        onImport={handleImportPresetJson}
                        onExport={handleExportPresetJson}
                        onError={setError}
                        deviceName={deviceName}
                        setDeviceName={setDeviceName}
                        onSaveDevice={handleSaveDevice}
                        onDeleteDevice={handleDeleteDevice}
                        problem={invalid ? previewError : null}
                        warnings={deviceWarnings}
                      />
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
                            min={limits.frame_to_phone_offset[0]}
                            max={limits.frame_to_phone_offset[1]}
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
                            min={limits.backplate_snap_clearance[0]}
                            max={limits.backplate_snap_clearance[1]}
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
                            min={limits.button_clearance[0]}
                            max={limits.button_clearance[1]}
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
                            min={limits.camera_ring_clearance[0]}
                            max={limits.camera_ring_clearance[1]}
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
                            min={limits.frame_wall[0]}
                            max={limits.frame_wall[1]}
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
                            min={limits.front_lip[0]}
                            max={limits.front_lip[1]}
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
                            min={limits.backplate_thickness[0]}
                            max={limits.backplate_thickness[1]}
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
                            min={limits.groove_depth[0]}
                            max={limits.groove_depth[1]}
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
                            min={limits.snap_engage[0]}
                            max={limits.snap_engage[1]}
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
                    {proTab === "pattern" && (
                      <div className="space-y-4">
                        <PatternPreviewCard request={patternPreview} colors={colors} typeLabel={patternTypeLabel} />
                        <PatternControls
                          config={config}
                          updateConfig={updateConfig}
                          uiMode={uiMode}
                          onError={setError}
                          specs={patternSpecs}
                          specsError={patternSpecsError}
                          onRetrySpecs={retryPatternSpecs}
                          gallery={patternGallery.data}
                          colors={colors}
                        />
                      </div>
                    )}

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
                          ...(hasRing ? [{ key: "camera_ring", label: "Camera Protection Ring" }] : []),
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
          <ViewportToolbar
            preview={preview}
            viewMode={viewMode}
            onViewMode={handleViewMode}
            onView={requestView}
            explode={explode}
            onExplode={setExplode}
            showPhoneGhost={showPhoneGhost}
            onTogglePhoneGhost={() => setShowPhoneGhost((v) => !v)}
            loading={loading}
            dirty={dirty && Boolean(preview)}
            canRebuild={Boolean(config)}
            onRebuild={refresh}
          />

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
                  <h2 className="text-sm font-semibold text-slate-200">Laser-cut backplate outline</h2>
                  <p className="text-xs text-slate-400">
                    Closed paths at 1:1 mm, seen from the back. Opens in LightBurn, Glowforge and similar tools.
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
              <Suspense
                fallback={
                  <div className="flex h-full w-full items-center justify-center bg-slate-950 text-xs text-slate-400">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading the 3D viewer…
                  </div>
                }
              >
                <Viewport3D
                  preview={preview}
                  viewMode={viewMode}
                  explode={explode}
                  colors={colors}
                  visibleGroups={visibleGroups}
                  showPhoneGhost={showPhoneGhost}
                  bed={preview?.bed}
                  viewRequest={viewRequest}
                  stale={dirty && Boolean(preview)}
                  hideHud
                />
              </Suspense>

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
                    ...(shownRing ? [{ key: "camera_ring", label: "Camera Ring" }] : []),
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
                      OCCT B-Rep: frame {preview.timings.frame}s · plate {preview.timings.backplate}s
                      {preview.summary?.has_camera_ring !== false && ` · ring ${preview.timings.camera_ring}s`} · btns{" "}
                      {preview.timings.buttons}s{preview.timings.mesh !== undefined && ` · mesh ${preview.timings.mesh}s`}
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
