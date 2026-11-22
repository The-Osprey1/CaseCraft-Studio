import { useCallback, useEffect, useRef, useState } from "react";
import { postJson } from "../api.js";

/**
 * POST the current design to one of the fast 2D pattern endpoints (/api/pattern-preview,
 * /api/pattern-gallery). They never wait for the CAD kernel, so answers take milliseconds even
 * while the 3D model is rebuilding.
 *
 * Latest wins, one request in flight: while a request runs, newer designs replace each other
 * as "pending" and the newest is sent as soon as the answer lands. A slider drag therefore
 * updates the drawing continuously (as fast as the server answers) and always settles on the
 * final value. `current` is true only when the data belongs to the latest design; after an
 * error the last good drawing is kept (the caller dims it) together with the message.
 */
export default function usePatternRequest(url, body, { delay = 30, enabled = true } = {}) {
  const key = enabled && body ? JSON.stringify(body) : null;
  const [state, setState] = useState({ key: null, data: null, error: null });
  const ref = useRef({ inflight: null, pending: null, timer: null, alive: true });

  const send = useCallback(
    (k) => {
      const r = ref.current;
      const ctl = new AbortController();
      r.inflight = ctl;
      postJson(url, JSON.parse(k), { signal: ctl.signal })
        .then((res) => res.json())
        .then((data) => {
          if (r.alive) setState({ key: k, data, error: null });
        })
        .catch((err) => {
          if (r.alive && err.name !== "AbortError") setState((s) => ({ key: k, data: s.data, error: err.message }));
        })
        .finally(() => {
          if (r.inflight === ctl) r.inflight = null;
          const next = r.pending;
          r.pending = null;
          if (next && r.alive) send(next);
        });
    },
    [url]
  );

  useEffect(() => {
    if (!key) return undefined;
    const r = ref.current;
    clearTimeout(r.timer);
    r.timer = setTimeout(() => {
      if (r.inflight) r.pending = key;
      else send(key);
    }, delay);
    return () => clearTimeout(r.timer);
  }, [key, delay, send]);

  useEffect(() => {
    const r = ref.current;
    r.alive = true;
    return () => {
      r.alive = false;
      clearTimeout(r.timer);
      r.inflight?.abort();
    };
  }, []);

  const current = Boolean(key) && state.key === key;
  return { data: state.data, error: current ? state.error : null, current, loading: Boolean(key) && !current };
}
