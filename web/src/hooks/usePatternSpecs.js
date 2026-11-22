import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api.js";

let cached = null; // the pattern library does not change while the app runs

/**
 * Pattern library metadata from the server (GET /api/patterns): every pattern type with its
 * defaults and control ranges, the border modes and the fonts. The pattern panel is built from
 * it, so a new generator on the server needs no UI change.
 */
export default function usePatternSpecs() {
  const [state, setState] = useState({ specs: cached, error: null });

  const load = useCallback(() => {
    setState({ specs: cached, error: null });
    apiFetch("/api/patterns")
      .then((r) => r.json())
      .then((data) => {
        cached = data;
        setState({ specs: data, error: null });
      })
      .catch((err) => setState({ specs: null, error: err.message }));
  }, []);

  useEffect(() => {
    if (!cached) load();
  }, [load]);

  return { ...state, retry: load };
}
