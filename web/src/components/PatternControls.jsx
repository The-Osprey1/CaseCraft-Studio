import React, { useMemo } from "react";
import { Loader2, RotateCcw, Upload } from "lucide-react";
import { FINISH_MODES, PATTERN_ICONS, SAMPLE_SVGS } from "../constants.jsx";
import { Segmented, SliderField, ToggleRow } from "./Fields.jsx";
import FilePickButton from "./FilePickButton.jsx";
import PlatePreview from "./PlatePreview.jsx";

// Per-type settings tuned in this session: switching hex -> dots -> hex brings the hex back.
const remembered = new Map();

function ArtworkPicker({ value, onPick, onError }) {
  const upload = (text, fileName) => {
    if (!/<svg[\s>]/i.test(text)) {
      onError?.(`${fileName} does not look like an SVG drawing.`);
      return;
    }
    onPick(text);
  };
  return (
    <div className="space-y-2">
      <FilePickButton
        accept=".svg,image/svg+xml"
        extensions={[".svg"]}
        onText={upload}
        onError={onError}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-cyan-500/50 bg-cyan-500/5 px-3 py-2.5 text-xs font-medium text-cyan-300 transition hover:bg-cyan-500/10"
      >
        <Upload className="h-3.5 w-3.5" />
        Upload an SVG drawing
      </FilePickButton>
      <div className="grid grid-cols-3 gap-1.5">
        {Object.entries(SAMPLE_SVGS).map(([k, item]) => (
          <button
            key={k}
            type="button"
            aria-pressed={value === item.svg}
            onClick={() => onPick(item.svg)}
            className={`rounded-lg border px-2 py-1.5 text-[11px] transition ${
              value === item.svg
                ? "border-cyan-400 bg-cyan-500/15 text-cyan-100"
                : "border-slate-700 bg-slate-950 text-slate-300 hover:border-cyan-500"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Control({ c, params, setParam, setParamNow, onError }) {
  const value = params?.[c.key];
  switch (c.kind) {
    case "slider":
      return (
        <SliderField
          label={c.label}
          value={value ?? c.min}
          min={c.min}
          max={c.max}
          step={c.step}
          unit={c.unit}
          hint={c.hint}
          onChange={(v) => setParam(c.key, v)}
        />
      );
    case "select":
      return (
        <label className="flex items-center justify-between gap-3 text-xs">
          <span className="text-slate-300">{c.label}</span>
          <select
            value={value ?? c.options[0]}
            onChange={(e) => setParamNow(c.key, e.target.value)}
            className="min-w-0 max-w-[60%] rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
          >
            {c.options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
      );
    case "text":
      return (
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-slate-300">{c.label}</span>
          <input
            type="text"
            maxLength={c.max_length}
            value={value ?? ""}
            onChange={(e) => setParam(c.key, e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
          />
        </label>
      );
    case "toggle":
      return (
        <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => setParamNow(c.key, e.target.checked)}
            className="accent-cyan-400"
          />
          {c.label}
        </label>
      );
    case "xy": {
      // stored in design coordinates; shown as seen from the back (+X = right)
      const sx = c.back_view_x ? -1 : 1;
      const [x, y] = Array.isArray(value) ? value : [0, 0];
      return (
        <div className="space-y-3">
          <SliderField
            label="Move left / right"
            value={sx * x}
            min={c.min}
            max={c.max}
            step={c.step}
            unit={c.unit}
            onChange={(v) => setParam(c.key, [sx * v, y])}
          />
          <SliderField
            label="Move down / up"
            value={y}
            min={c.min}
            max={c.max}
            step={c.step}
            unit={c.unit}
            onChange={(v) => setParam(c.key, [x, v])}
          />
        </div>
      );
    }
    case "svg":
      return <ArtworkPicker value={value} onPick={(svg) => setParamNow(c.key, svg)} onError={onError} />;
    default:
      return null;
  }
}

/**
 * Backplate pattern panel, built from the server's pattern library (GET /api/patterns):
 * a gallery of every pattern drawn on this phone, the finish, the border treatment, the
 * type's own settings, corner rounding, and the MagSafe pocket.
 */
export default function PatternControls({ config, updateConfig, uiMode, onError, specs, specsError, onRetrySpecs,
                                          gallery, colors }) {
  const types = specs?.types || [];
  const pat = config?.pattern;
  const spec = types.find((t) => t.id === pat?.type);
  const galleryFrame = useMemo(() => (gallery ? { ...gallery, magsafe: "", lanyard: "" } : null), [gallery]);

  if (!config) return null;
  if (!specs) {
    return specsError ? (
      <div className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-3 text-xs text-rose-200">
        Could not load the pattern library: {specsError}
        <button
          type="button"
          onClick={onRetrySpecs}
          className="mt-2 flex items-center gap-1.5 rounded-lg border border-rose-400/40 px-2.5 py-1 text-rose-100 hover:bg-rose-500/10"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Try again
        </button>
      </div>
    ) : (
      <div className="flex items-center gap-2 py-6 text-xs text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading patterns…
      </div>
    );
  }

  const set = (fn, immediate = false) =>
    updateConfig((c) => {
      fn(c.pattern, c);
      return c;
    }, immediate);
  const setParam = (key, v) => set((p) => (p.params = { ...p.params, [key]: v }));
  const setParamNow = (key, v) => set((p) => (p.params = { ...p.params, [key]: v }), true);

  const selectType = (id) => {
    if (id === pat.type) return;
    remembered.set(pat.type, pat.params);
    const next = types.find((t) => t.id === id);
    set((p) => {
      p.type = id;
      p.params = structuredClone(remembered.get(id) || next.defaults);
    }, true);
  };

  const isEmblem = spec?.family === "emblem";
  const edges = (specs.edges || []).filter((e) => spec?.edges?.includes(e.id));
  const edge = pat.edge ?? "clip";
  const shared = specs.shared || {};
  const finish = FINISH_MODES.find((m) => m.id === pat.mode);

  return (
    <div className="space-y-5">
      <section className="space-y-2" aria-label="Pattern">
        <div className="grid grid-cols-4 gap-1.5">
          {types.map((t) => {
            const active = pat.type === t.id;
            const thumb = gallery?.types?.[t.id];
            return (
              <button
                key={t.id}
                type="button"
                aria-pressed={active}
                title={t.description}
                onClick={() => selectType(t.id)}
                className={`flex flex-col items-center gap-1 rounded-xl border px-1 pb-1.5 pt-2 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
                  active
                    ? "border-cyan-400 bg-cyan-500/10 ring-1 ring-cyan-400/30"
                    : "border-slate-800 bg-slate-900/60 hover:border-slate-600"
                }`}
              >
                <span className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-lg text-slate-500">
                  {thumb && galleryFrame ? (
                    <PlatePreview
                      frame={galleryFrame}
                      cuts={thumb.cuts}
                      colors={colors}
                      mode={pat.mode}
                      crop="middle"
                      className="h-full w-full"
                      label={`${t.label} pattern`}
                    />
                  ) : (
                    PATTERN_ICONS[t.id]
                  )}
                </span>
                <span
                  className={`text-center text-[11px] font-medium leading-tight ${active ? "text-cyan-100" : "text-slate-300"}`}
                >
                  {t.label}
                </span>
              </button>
            );
          })}
        </div>
        {spec && <p className="text-[11px] text-slate-400">{spec.description}.</p>}
      </section>

      {pat.type !== "solid" && (
        <>
          <Segmented
            label="Finish"
            options={FINISH_MODES}
            value={pat.mode}
            onChange={(id) => set((p) => (p.mode = id), true)}
            hint={finish?.desc}
          />

          {edges.length > 0 && (
            <div className="space-y-3">
              <Segmented
                label="Border"
                options={edges}
                value={edge}
                onChange={(id) => set((p) => (p.edge = id), true)}
                hint={edges.find((e) => e.id === edge)?.description}
              />
              {edge === "fade" && shared.fade_width && (
                <SliderField
                  {...shared.fade_width}
                  value={pat.fade_width ?? 15}
                  onChange={(v) => set((p) => (p.fade_width = v))}
                />
              )}
            </div>
          )}

          {spec?.controls?.length > 0 && (
            <section className="space-y-3.5 rounded-xl border border-slate-800 bg-slate-900/70 p-3.5" aria-label={`${spec.label} settings`}>
              {spec.controls.map((c) => (
                <Control
                  key={c.key}
                  c={c}
                  params={pat.params}
                  setParam={setParam}
                  setParamNow={setParamNow}
                  onError={onError}
                />
              ))}
            </section>
          )}

          {spec?.rounding && shared.corner_radius && (
            <SliderField
              {...shared.corner_radius}
              value={pat.corner_radius ?? 0}
              onChange={(v) => set((p) => (p.corner_radius = v))}
            />
          )}

          {pat.mode === "through" && isEmblem && (
            <ToggleRow
              label="Stencil bridges"
              hint="Thin bridges hold the middles of O, A and B in place"
              checked={pat.stencil_bridges ?? true}
              onChange={(v) => set((p) => (p.stencil_bridges = v), true)}
            />
          )}

          {uiMode === "pro" && (
            <section className="space-y-3 border-t border-slate-800/80 pt-3" aria-label="Pattern limits">
              {shared.margin && (
                <SliderField {...shared.margin} value={pat.margin} onChange={(v) => set((p) => (p.margin = v))} />
              )}
              {shared.web && <SliderField {...shared.web} value={pat.web} onChange={(v) => set((p) => (p.web = v))} />}
              {pat.mode !== "through" && (
                <SliderField
                  label="Deboss / inlay depth"
                  value={pat.depth}
                  min={0.4}
                  max={Math.max(0.4, (config.style?.backplate_thickness ?? 1.8) - 0.6)}
                  step={0.1}
                  onChange={(v) => set((p) => (p.depth = v))}
                />
              )}
            </section>
          )}
        </>
      )}

      <ToggleRow
        label="MagSafe magnet pocket"
        hint={`${config.style?.magsafe_depth ?? 0.75} mm pocket for a 54 mm magnet ring and its alignment tail`}
        checked={config.style?.magsafe_ring}
        onChange={(v) =>
          updateConfig((c) => {
            c.style.magsafe_ring = v;
            return c;
          }, true)
        }
      />
      {config.style?.magsafe_ring && (
        <SliderField
          label="MagSafe ring position"
          value={config.style?.magsafe_offset_y ?? 0}
          min={-30}
          max={30}
          step={0.5}
          hint="Negative moves the ring towards the bottom. Line it up with your phone's charging coil and keep it clear of the camera."
          onChange={(v) =>
            updateConfig((c) => {
              c.style.magsafe_offset_y = v;
              return c;
            })
          }
        />
      )}

      <ToggleRow
        label="Lanyard tether pocket"
        hint="A recess on the inside of the backplate for a lanyard card; the strap leaves through the charging port. Patterns stay off it (dashed outline)."
        checked={config.style?.lanyard_pocket}
        onChange={(v) =>
          updateConfig((c) => {
            c.style.lanyard_pocket = v;
            return c;
          }, true)
        }
      />
      {config.style?.lanyard_pocket && uiMode === "pro" && (
        <SliderField
          label="Lanyard pocket depth"
          value={config.style?.lanyard_depth ?? 0.65}
          min={0.4}
          max={Math.max(0.4, Math.min(0.9, (config.style?.backplate_thickness ?? 1.8) - 0.6))}
          step={0.05}
          hint="Leaves at least 0.6 mm of backplate floor"
          onChange={(v) =>
            updateConfig((c) => {
              c.style.lanyard_depth = v;
              return c;
            })
          }
        />
      )}
    </div>
  );
}
