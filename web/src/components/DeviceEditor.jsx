import React, { useMemo, useState } from "react";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import DeviceDiagram from "./DeviceDiagram.jsx";
import { DeviceSelect, deviceBrand, MY_DEVICES, OTHER_BRAND } from "./DevicePicker.jsx";
import FilePickButton from "./FilePickButton.jsx";
import { NumberField, Segmented } from "./Fields.jsx";
import { cleanDeviceName } from "../constants.jsx";

const SIDES = ["left", "right", "top", "bottom"];
const VERIFICATION_LEVELS = [
  { id: "approximate", label: "Approximate", desc: "Not measured, or measured roughly" },
  { id: "dimensionally_verified", label: "Measured", desc: "Checked with calipers or against the maker's drawing" },
  { id: "physically_fit_tested", label: "Fit-tested", desc: "A printed case fitted the real phone (needs a passed fit test)" },
];

function Section({ title, children, aside }) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function SmallButton({ children, onClick, tone = "cyan", title }) {
  const tones = {
    cyan: "text-cyan-300 hover:border-cyan-500",
    violet: "text-violet-300 hover:border-violet-400",
    rose: "text-rose-300 hover:border-rose-400",
    slate: "text-slate-300 hover:border-slate-500",
  };
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`flex items-center gap-1 rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

function TextInput({ label, value, onChange, placeholder, list, maxLength = 80 }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] text-slate-400">{label}</span>
      <input
        value={value ?? ""}
        list={list}
        maxLength={maxLength}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-500"
      />
    </label>
  );
}

/**
 * Pro mode "Device" tab: everything about the phone itself, edited against a live sketch.
 * Values are committed as you type once they are valid; the CAD preview validates the whole
 * design and its problems are listed at the top.
 */
export default function DeviceEditor({
  config,
  presets,
  userPresetIds,
  updateConfig,
  onSelectPreset,
  onImport,
  onExport,
  onError,
  deviceName,
  setDeviceName,
  onSaveDevice,
  onDeleteDevice,
  problem,
  warnings = [],
}) {
  const [focus, setFocus] = useState(null);
  const track = (key) => (on) => setFocus(on ? key : null);
  const brands = useMemo(
    () =>
      [...new Set(presets.map((p) => deviceBrand(p, [])).filter((b) => b !== OTHER_BRAND && b !== MY_DEVICES))].sort(),
    [presets]
  );
  const isUser = userPresetIds.includes(config.id);
  const known = presets.some((p) => p.id === config.id);
  const set = (path, immediate = false) => (v) =>
    updateConfig((c) => {
      let o = c;
      for (const k of path.slice(0, -1)) o = o[k];
      o[path[path.length - 1]] = v;
      return c;
    }, immediate);
  const cam = config.camera;
  const v = config.verification || { level: "approximate", fit_test: "untested", source: "", notes: "" };

  return (
    <div className="space-y-5">
      {/* ---- device library */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Start from</label>
          <div className="flex items-center gap-1.5">
            <FilePickButton
              accept=".json,application/json"
              extensions={[".json"]}
              onText={onImport}
              onError={onError}
              className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300 hover:border-cyan-500"
            >
              Import JSON
            </FilePickButton>
            <SmallButton onClick={onExport}>Export JSON</SmallButton>
          </div>
        </div>
        <DeviceSelect
          presets={presets}
          userPresetIds={userPresetIds}
          value={config.id}
          unsavedLabel={!known ? `${cleanDeviceName(config.name)} (unsaved)` : null}
          onChange={onSelectPreset}
          className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-100 outline-none focus:border-cyan-500"
        />
        {deviceName === null ? (
          <div className="flex items-center gap-1.5">
            <SmallButton
              tone="violet"
              onClick={() => setDeviceName(isUser ? config.name : `My ${cleanDeviceName(config.name)}`)}
              title="Keep these measurements in My devices"
            >
              Save as my device…
            </SmallButton>
            {isUser && (
              <SmallButton tone="rose" onClick={onDeleteDevice}>
                Delete my device
              </SmallButton>
            )}
          </div>
        ) : (
          <form
            className="flex items-center gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              onSaveDevice();
            }}
          >
            <input
              autoFocus
              value={deviceName}
              maxLength={80}
              onChange={(e) => setDeviceName(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setDeviceName(null)}
              placeholder="Device name"
              aria-label="Name for your saved device"
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

      <DeviceDiagram config={config} highlight={focus} />

      {(problem || warnings.length > 0) && (
        <div
          role="status"
          className={`space-y-1 rounded-lg border px-3 py-2 text-[11px] ${
            problem ? "border-rose-500/40 bg-rose-950/40 text-rose-200" : "border-amber-500/30 bg-amber-950/30 text-amber-200"
          }`}
        >
          <div className="flex items-center gap-1.5 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" />
            {problem ? "This device can't be built yet" : "Check before printing"}
          </div>
          {problem && <p className="break-words">{problem}</p>}
          {warnings.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4 text-amber-200/90">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ---- identity */}
      <Section title="Device">
        <div className="grid grid-cols-2 gap-2.5">
          <div className="col-span-2">
            <TextInput label="Model name" value={config.name} onChange={set(["name"])} placeholder="e.g. Pixel 10 Pro" />
          </div>
          <TextInput label="Maker" value={config.brand} onChange={set(["brand"])} placeholder="e.g. Google" list="casecraft-brands" />
          <NumberField
            label="Release year"
            value={config.year || 0}
            min={0}
            max={2100}
            step={1}
            unit=""
            hint="0 = unknown"
            onChange={(y) => set(["year"])(Math.round(y))}
          />
          <datalist id="casecraft-brands">
            {brands.map((b) => (
              <option key={b} value={b} />
            ))}
          </datalist>
        </div>
      </Section>

      {/* ---- body */}
      <Section title="Body (calipers)">
        <div className="grid grid-cols-2 gap-2.5">
          <NumberField label="Length (L)" value={config.body.length} min={80} max={220} onChange={set(["body", "length"])} onFocusChange={track("body")} />
          <NumberField label="Width (W)" value={config.body.width} min={50} max={120} onChange={set(["body", "width"])} onFocusChange={track("body")} />
          <NumberField label="Thickness (T)" value={config.body.thickness} min={4} max={20} step={0.05} onChange={set(["body", "thickness"])} onFocusChange={track("body")} hint="Without the camera bump" />
          <NumberField label="Corner radius (R)" value={config.body.corner_radius} min={0} max={35} onChange={set(["body", "corner_radius"])} onFocusChange={track("body")} hint="Seen from the back" />
        </div>
      </Section>

      {/* ---- camera */}
      <Section title="Camera island">
        <Segmented
          label="How the case meets the camera"
          options={[
            { id: "ring", label: "Press-fit ring" },
            { id: "open", label: "Open cut-out" },
          ]}
          value={cam.ring === false ? "open" : "ring"}
          onChange={(id) => set(["camera", "ring"], true)(id === "ring")}
          hint={
            cam.ring === false
              ? "The backplate simply clears the island and may open through its edge: for islands that reach the edge and full-width camera plateaus. No raised guard around the lenses."
              : "A separate ring with a raised bezel presses into the backplate around the island. Needs room for the ring between the island and the phone edge."
          }
        />
        <div className="grid grid-cols-3 gap-2">
          <NumberField label="X from left" value={cam.x} min={0} onChange={set(["camera", "x"])} onFocusChange={track("camera")} />
          <NumberField label="Y from top" value={cam.y} min={0} onChange={set(["camera", "y"])} onFocusChange={track("camera")} />
          <NumberField label="Corner R" value={cam.radius} min={0} onChange={set(["camera", "radius"])} onFocusChange={track("camera")} />
          <NumberField label="Width" value={cam.width} min={1} onChange={set(["camera", "width"])} onFocusChange={track("camera")} />
          <NumberField label="Height" value={cam.height} min={1} onChange={set(["camera", "height"])} onFocusChange={track("camera")} />
        </div>
        <p className="text-[10px] text-slate-500">
          Measured on the back, from its top-left corner, at the island's base. A full-width plateau is X 0, Y 0, Width = body width.
        </p>
        {cam.ring !== false && (
          <>
            <label className="flex cursor-pointer items-center gap-2 text-[11px] text-slate-300">
              <input
                type="checkbox"
                checked={Boolean(cam.opening)}
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
              Separate outer-opening profile (island wider at its base, or a flared opening)
            </label>
            {cam.opening && (
              <div className="grid grid-cols-3 gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-2">
                {[
                  ["width", "Opening W", 1],
                  ["height", "Opening H", 1],
                  ["radius", "Opening R", 0],
                  ["dx", "Shift X", undefined],
                  ["dy", "Shift Y", undefined],
                ].map(([k, label, min]) => (
                  <NumberField
                    key={k}
                    label={label}
                    value={cam.opening[k]}
                    min={min}
                    onChange={set(["camera", "opening", k])}
                    onFocusChange={track("camera")}
                  />
                ))}
                <p className="col-span-3 text-[10px] text-slate-500">
                  The clear opening at the ring's outer face. Shift is measured on the back view (+X right, +Y down).
                </p>
              </div>
            )}
          </>
        )}
      </Section>

      {/* ---- buttons */}
      <Section
        title={`Buttons (${config.buttons.length})`}
        aside={
          <SmallButton
            onClick={() =>
              updateConfig((c) => {
                const n = c.buttons.length + 1;
                c.buttons.push({ id: `button_${n}`, side: "right", pos: Math.min(60, c.body.length / 2), length: 10 });
                return c;
              }, true)
            }
          >
            <Plus className="h-3 w-3" /> Add
          </SmallButton>
        }
      >
        <p className="text-[10px] text-slate-500">
          Side as seen from the screen. Position = distance from the top (left/right side) or from the left (top/bottom) to where the button starts.
        </p>
        {config.buttons.map((b, idx) => (
          <div key={idx} className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
            <div className="flex items-center gap-2">
              <input
                value={b.id}
                aria-label="Button name"
                onChange={(e) => set(["buttons", idx, "id"])(e.target.value)}
                onFocus={() => setFocus(`button:${idx}`)}
                onBlur={() => setFocus(null)}
                className="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-100"
              />
              <select
                value={b.side}
                aria-label="Side"
                onChange={(e) => set(["buttons", idx, "side"], true)(e.target.value)}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-200"
              >
                {SIDES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label={`Remove button ${b.id}`}
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
              <NumberField label="Starts at" value={b.pos} min={0} step={0.5} onChange={set(["buttons", idx, "pos"])} onFocusChange={track(`button:${idx}`)} />
              <NumberField label="Length" value={b.length} min={1} step={0.5} onChange={set(["buttons", idx, "length"])} onFocusChange={track(`button:${idx}`)} />
            </div>
          </div>
        ))}
      </Section>

      {/* ---- ports */}
      <Section
        title={`Ports & openings (${config.ports.length})`}
        aside={
          <SmallButton
            onClick={() =>
              updateConfig((c) => {
                c.ports.push({ id: `port_${c.ports.length + 1}`, side: "bottom", center: 0, width: 10, height: 3, radius: 1.4, z_offset: 0 });
                return c;
              }, true)
            }
          >
            <Plus className="h-3 w-3" /> Add
          </SmallButton>
        }
      >
        <p className="text-[10px] text-slate-500">
          Centre = offset from the middle of that edge (+ is towards the right on top/bottom, towards the top on the sides). Height is across the phone's thickness.
        </p>
        {config.ports.map((pt, idx) => (
          <div key={idx} className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
            <div className="flex items-center gap-2">
              <input
                value={pt.id}
                aria-label="Port name"
                onChange={(e) => set(["ports", idx, "id"])(e.target.value)}
                onFocus={() => setFocus(`port:${idx}`)}
                onBlur={() => setFocus(null)}
                className="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-100"
              />
              <select
                value={pt.side}
                aria-label="Side"
                onChange={(e) => set(["ports", idx, "side"], true)(e.target.value)}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-200"
              >
                {SIDES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label={`Remove port ${pt.id}`}
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
              <NumberField label="Centre" value={pt.center} step={0.5} onChange={set(["ports", idx, "center"])} onFocusChange={track(`port:${idx}`)} />
              <NumberField label="Width" value={pt.width} min={0.5} step={0.5} onChange={set(["ports", idx, "width"])} onFocusChange={track(`port:${idx}`)} />
              <NumberField label="Height" value={pt.height} min={0.5} step={0.5} onChange={set(["ports", idx, "height"])} onFocusChange={track(`port:${idx}`)} />
              <NumberField label="Corner R" value={pt.radius} min={0} step={0.1} onChange={set(["ports", idx, "radius"])} onFocusChange={track(`port:${idx}`)} />
              <NumberField
                label="Height offset"
                value={pt.z_offset ?? 0}
                step={0.1}
                hint="+ towards the screen"
                onChange={set(["ports", idx, "z_offset"])}
                onFocusChange={track(`port:${idx}`)}
              />
            </div>
          </div>
        ))}
      </Section>

      {/* ---- provenance */}
      <Section title="How was this measured?">
        <Segmented
          label="Dimensions"
          options={VERIFICATION_LEVELS.map(({ id, label }) => ({ id, label }))}
          value={v.level}
          onChange={(level) =>
            updateConfig((c) => {
              c.verification = { ...v, level, fit_test: level === "physically_fit_tested" ? "passed" : v.fit_test };
              return c;
            }, true)
          }
          hint={VERIFICATION_LEVELS.find((x) => x.id === v.level)?.desc}
        />
        <TextInput
          label="Source"
          value={v.source}
          maxLength={200}
          placeholder="e.g. Digital calipers, 2026-11-22"
          onChange={(source) =>
            updateConfig((c) => {
              c.verification = { ...v, source };
              return c;
            })
          }
        />
      </Section>
    </div>
  );
}
