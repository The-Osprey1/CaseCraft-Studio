import { useCallback, useEffect, useRef, useState } from "react";
import { IS_DESKTOP, call, confirmAction } from "../desktop.js";

export const PROJECT_FORMAT = "casecraft-project";
export const PROJECT_VERSION = 1;
const AUTOSAVE_DELAY_MS = 2000;

/** Identity of everything a project file stores; "dirty" = differs from the last save/open. */
export function designSnapshot(f) {
  return JSON.stringify([f.config, f.printerId, f.themeId, f.colors, f.couponType, f.calId]);
}

/**
 * Desktop project handling: New / Open / Save / Save As, the recent list, dirty tracking (window
 * title + close confirmation), crash-safe autosave and the restore offer after a crash.
 *
 * fields:       {config, printerId, themeId, colors, couponType, calId} -- the live design
 * ready:        presets/printers are loaded (safe to open projects)
 * applyProject: (data) => void   load a project's fields into the UI
 * resetDesign:  () => void       back to the default untitled design
 */
export default function useProject({ fields, ready, applyProject, resetDesign, onError, onNotice }) {
  const [path, setPath] = useState(null);
  const [name, setName] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [recent, setRecent] = useState([]);
  const [restoreOffer, setRestoreOffer] = useState(null); // {savedAt, data}
  const [applyTick, setApplyTick] = useState(0);
  const pendingBaselineRef = useRef(false);
  const autosavedRef = useRef(false);
  const startedRef = useRef(false);

  const snapshot = fields.config ? designSnapshot(fields) : null;
  const dirty = snapshot !== null && baseline !== null && snapshot !== baseline;

  // The first design shown (the default preset) is the clean baseline of an untitled project;
  // after New/Open the baseline is re-taken once the loaded fields have rendered.
  useEffect(() => {
    if (!snapshot) return;
    if (baseline === null || pendingBaselineRef.current) {
      pendingBaselineRef.current = false;
      setBaseline(snapshot);
    }
  }, [snapshot, applyTick, baseline]);

  const buildData = useCallback(
    () => ({
      format: PROJECT_FORMAT,
      version: PROJECT_VERSION,
      name: name || fields.config?.id || "case",
      config: fields.config,
      printerId: fields.printerId,
      themeId: fields.themeId,
      colors: fields.colors,
      couponType: fields.couponType,
      calId: fields.calId,
    }),
    [name, fields]
  );

  // ---- desktop window state
  useEffect(() => {
    if (IS_DESKTOP) call("set_dirty", dirty);
  }, [dirty]);
  useEffect(() => {
    if (IS_DESKTOP) call("set_title", `${dirty ? "● " : ""}${name || "Untitled"}`);
  }, [dirty, name]);

  const buildDataRef = useRef(buildData);
  buildDataRef.current = buildData;

  // ---- autosave (paused while a crash-restore offer is open, so it cannot be overwritten).
  // Keyed on the design snapshot, so unrelated re-renders don't restart the timer.
  useEffect(() => {
    if (!IS_DESKTOP || !snapshot || restoreOffer) return undefined;
    if (!dirty) {
      if (autosavedRef.current) {
        autosavedRef.current = false;
        call("clear_autosave");
      }
      return undefined;
    }
    const t = setTimeout(() => {
      autosavedRef.current = true;
      call("autosave", buildDataRef.current());
    }, AUTOSAVE_DELAY_MS);
    return () => clearTimeout(t);
  }, [snapshot, dirty, restoreOffer]);

  const refreshRecent = useCallback(async () => {
    if (!IS_DESKTOP) return;
    const r = await call("recent_projects");
    if (r.ok) setRecent(r.items);
  }, []);

  const applyLoaded = (data, { path: p, name: n, clean = true }) => {
    applyProject(data);
    setPath(p || null);
    setName(n || null);
    if (clean) {
      pendingBaselineRef.current = true;
      setApplyTick((t) => t + 1);
    } else {
      setBaseline("\u0000recovered"); // never equal to a real snapshot -> dirty until saved
    }
  };

  const confirmDiscard = async () =>
    !dirty || (await confirmAction("Discard the unsaved changes to the current design?"));

  const openProject = async (p = null, { skipConfirm = false } = {}) => {
    if (!skipConfirm && !(await confirmDiscard())) return;
    const r = await call("open_project", p);
    if (!r.ok) {
      if (!r.cancelled) onError(r.error);
      refreshRecent();
      return;
    }
    setRestoreOffer(null);
    applyLoaded(r.data, { path: r.path, name: r.name });
    refreshRecent();
    onNotice({ text: `Opened ${r.name}` });
  };

  const save = async (saveAs = false) => {
    if (!fields.config) return;
    const snap = snapshot;
    const r = await call("save_project", buildData(), saveAs ? null : path);
    if (!r.ok) {
      if (!r.cancelled) onError(r.error);
      return;
    }
    setPath(r.path);
    setName(r.name);
    setBaseline(snap);
    autosavedRef.current = false;
    call("clear_autosave");
    refreshRecent();
    onNotice({ text: `Saved ${r.name}.casecraft`, path: r.path });
  };

  const newProject = async () => {
    if (!(await confirmDiscard())) return;
    resetDesign();
    setPath(null);
    setName(null);
    pendingBaselineRef.current = true;
    setApplyTick((t) => t + 1);
  };

  const restore = () => {
    if (!restoreOffer) return;
    const data = restoreOffer.data;
    setRestoreOffer(null);
    applyLoaded(data, { path: null, name: data.name ? `${data.name} (recovered)` : "Recovered design", clean: false });
  };

  const discardRestore = () => {
    setRestoreOffer(null);
    call("clear_autosave");
  };

  // ---- start-up: a project passed on the command line wins over the crash-restore offer
  const openRef = useRef(openProject);
  openRef.current = openProject;
  useEffect(() => {
    if (!IS_DESKTOP || !ready || startedRef.current) return;
    startedRef.current = true;
    (async () => {
      refreshRecent();
      const pending = await call("take_pending_open");
      if (pending.ok && pending.path) {
        await openRef.current(pending.path, { skipConfirm: true });
        return;
      }
      const a = await call("load_autosave");
      if (a.ok && a.found) setRestoreOffer({ savedAt: a.saved_at, data: a.data });
    })();
  }, [ready, refreshRecent]);

  // A .casecraft file double-clicked while the app is already open arrives here.
  useEffect(() => {
    if (!IS_DESKTOP) return undefined;
    window.__casecraftOpenProject = (p) => openRef.current(p);
    return () => {
      delete window.__casecraftOpenProject;
    };
  }, []);

  // ---- keyboard shortcuts
  const actionsRef = useRef({});
  actionsRef.current = { save, openProject, newProject };
  useEffect(() => {
    if (!IS_DESKTOP) return undefined;
    const onKey = (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "s") {
        e.preventDefault();
        actionsRef.current.save(e.shiftKey);
      } else if (k === "o") {
        e.preventDefault();
        actionsRef.current.openProject();
      } else if (k === "n") {
        e.preventDefault();
        actionsRef.current.newProject();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return {
    enabled: IS_DESKTOP,
    path,
    name: name || "Untitled",
    dirty,
    recent,
    refreshRecent,
    restoreOffer,
    restore,
    discardRestore,
    newProject,
    openProject,
    save: () => save(false),
    saveAs: () => save(true),
    clearRecent: async () => {
      await call("clear_recent");
      refreshRecent();
    },
  };
}
