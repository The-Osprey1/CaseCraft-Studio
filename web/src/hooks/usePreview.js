import { useCallback, useEffect, useRef, useState } from "react";
import { designKey, postJson } from "../api.js";

const CACHE_MAX = 12;

/**
 * CAD preview requests for the current config + printer profile.
 *
 * - Debounced: `delayRef.current` (ms) is read when a change is scheduled, so discrete clicks can
 *   be near-immediate while slider drags wait.
 * - Cancelled: a newer request aborts the in-flight one, so an older response can never replace
 *   a newer configuration's preview.
 * - Keyed: every result carries the design key it was computed for; `isCurrent` is true only when
 *   that key equals the live config + printer. Exports and the validation badge rely on it.
 * - Cached: a small client cache makes undo-like toggles instant (the server caches too).
 */
export default function usePreview(config, printerId, delayRef) {
  const [state, setState] = useState({ status: "idle", data: null, error: null, invalid: false, key: null });
  const abortRef = useRef(null);
  const timerRef = useRef(null);
  const cacheRef = useRef(new Map());
  const key = designKey(config, printerId);

  const run = useCallback((cfg, pid, k, { force = false } = {}) => {
    if (!cfg) return;
    abortRef.current?.abort();
    const cache = cacheRef.current;
    if (!force && cache.has(k)) {
      const data = cache.get(k);
      cache.delete(k);
      cache.set(k, data); // LRU touch
      setState({ status: "ready", data, error: null, invalid: false, key: k });
      return;
    }
    const ctl = new AbortController();
    abortRef.current = ctl;
    setState((s) => ({ ...s, status: "loading", error: null, invalid: false, key: k }));
    postJson(`/api/generate-preview?printer=${encodeURIComponent(pid)}`, cfg, { signal: ctl.signal })
      .then((res) => res.json())
      .then((data) => {
        if (ctl.signal.aborted) return;
        cache.set(k, data);
        while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
        setState({ status: "ready", data, error: null, invalid: false, key: k });
      })
      .catch((err) => {
        if (err.name === "AbortError" || ctl.signal.aborted) return;
        // keep the last good geometry on screen, but mark it as not current
        setState((s) => ({ status: "error", data: s.data, error: err.message, invalid: Boolean(err.invalid), key: k }));
      });
  }, []);

  useEffect(() => {
    if (!key) return undefined;
    clearTimeout(timerRef.current);
    const delay = delayRef?.current ?? 450;
    timerRef.current = setTimeout(() => run(config, printerId, key), delay);
    return () => clearTimeout(timerRef.current);
    // config/printerId are fully captured by `key`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, run]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const refresh = useCallback(() => run(config, printerId, key, { force: true }), [run, config, printerId, key]);

  const isCurrent = state.key === key && state.status === "ready";
  return {
    preview: state.data,
    status: state.key === key ? state.status : "loading", // a pending change counts as loading
    error: state.key === key ? state.error : null,
    invalid: state.key === key && state.invalid,
    isCurrent,
    refresh,
  };
}
