import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, FilePlus2, FolderOpen, HelpCircle, History, Save } from "lucide-react";
import { call, copyDiagnostics } from "../desktop.js";

function Item({ icon: Icon, label, hint, onClick, disabled }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 text-slate-400" /> : <span className="w-3.5" />}
      <span className="flex-1 truncate">{label}</span>
      {hint && <span className="font-mono text-[10px] text-slate-500">{hint}</span>}
    </button>
  );
}

const Divider = () => <div className="my-1 border-t border-slate-800" />;

/** Desktop-only File/Help menu with the project name and unsaved-changes dot. */
export default function FileMenu({ project, onNotice, onError }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    project.refreshRecent();
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!project.enabled) return null;
  const act = (fn) => () => {
    setOpen(false);
    fn();
  };
  const about = async () => {
    const r = await call("app_info");
    if (r.ok) onNotice({ text: `CaseCraft Studio ${r.version} · data: ${r.data_dir}` });
  };
  const diag = async () => {
    const r = await copyDiagnostics();
    if (r.ok) onNotice({ text: "Diagnostics copied to the clipboard" });
    else onError(r.error);
  };
  const recent = project.recent || [];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={project.path || "Not saved yet"}
        className="flex max-w-[220px] items-center gap-1.5 rounded-lg border border-slate-700/80 bg-slate-800/80 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
      >
        <span className="truncate">{project.name}</span>
        {project.dirty && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" title="Unsaved changes" />}
        <ChevronDown className="h-3 w-3 shrink-0 text-slate-400" />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-64 rounded-xl border border-slate-800 bg-slate-900 p-1.5 shadow-2xl">
          <Item icon={FilePlus2} label="New design" hint="Ctrl+N" onClick={act(project.newProject)} />
          <Item icon={FolderOpen} label="Open project…" hint="Ctrl+O" onClick={act(() => project.openProject())} />
          <Item icon={Save} label="Save" hint="Ctrl+S" onClick={act(project.save)} />
          <Item label="Save as…" hint="Ctrl+Shift+S" onClick={act(project.saveAs)} />
          <Divider />
          <div className="flex items-center gap-2 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <History className="h-3 w-3" /> Recent
          </div>
          {recent.length === 0 && <div className="px-2.5 py-1 text-[11px] text-slate-500">No recent projects</div>}
          {recent.map((r) => (
            <Item
              key={r.path}
              label={r.name}
              disabled={!r.exists}
              hint={r.exists ? "" : "missing"}
              onClick={act(() => project.openProject(r.path))}
            />
          ))}
          {recent.length > 0 && <Item label="Clear recent list" onClick={act(project.clearRecent)} />}
          <Divider />
          <Item icon={HelpCircle} label="Copy diagnostics" onClick={act(diag)} />
          <Item label="Open log folder" onClick={act(() => call("open_log_folder"))} />
          <Item label="Open my data folder" onClick={act(() => call("open_data_folder"))} />
          <Item label="About CaseCraft Studio" onClick={act(about)} />
        </div>
      )}
    </div>
  );
}
