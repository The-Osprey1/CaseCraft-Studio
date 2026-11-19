import React from "react";
import { IS_DESKTOP, copyDiagnostics } from "../desktop.js";

/** Last line of defence for render errors: a recoverable screen instead of a blank window. */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, copied: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("CaseCraft UI crashed", error, info?.componentStack);
  }

  render() {
    const { error, copied } = this.state;
    if (!error) return this.props.children;
    const copy = async () => {
      const r = await copyDiagnostics();
      this.setState({ copied: r.ok ? "Copied" : r.error });
    };
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-950 p-6 text-slate-100">
        <div className="max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-7 shadow-2xl">
          <h1 className="text-base font-semibold text-white">Something went wrong</h1>
          <p className="mt-2 text-sm text-slate-400">
            The CaseCraft Studio interface hit an unexpected error.
            {IS_DESKTOP && " Your design is autosaved; reload to restore it."}
          </p>
          <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-3 text-[11px] text-rose-300">
            {String(error?.message || error)}
          </pre>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-lg bg-cyan-500 px-3.5 py-1.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400"
            >
              Reload
            </button>
            {IS_DESKTOP && (
              <button
                type="button"
                onClick={copy}
                className="rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
              >
                {copied || "Copy diagnostics"}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }
}
