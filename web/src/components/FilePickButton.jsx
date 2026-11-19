import React, { useRef } from "react";
import { IS_DESKTOP, call } from "../desktop.js";

const MAX_BYTES = 10 * 1024 * 1024;

/**
 * Pick a text file: the native Open dialog in the desktop app, <input type="file"> in a browser.
 * Calls onText(text, fileName); problems go to onError(message).
 */
export default function FilePickButton({ accept, extensions, onText, onError, className, children, title }) {
  const inputRef = useRef(null);

  if (IS_DESKTOP) {
    const pick = async () => {
      const r = await call("open_file", extensions);
      if (r.ok) onText(r.text, r.name);
      else if (!r.cancelled) onError?.(r.error);
    };
    return (
      <button type="button" onClick={pick} className={className} title={title}>
        {children}
      </button>
    );
  }

  const onChange = (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // picking the same file again must fire onChange again
    if (!file) return;
    if (file.size > MAX_BYTES) {
      onError?.(`${file.name} is too large (limit 10 MB).`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => onText(String(reader.result || ""), file.name);
    reader.onerror = () => onError?.(`Could not read ${file.name}.`);
    reader.readAsText(file);
  };

  return (
    <label className={`cursor-pointer ${className || ""}`} title={title}>
      {children}
      <input ref={inputRef} type="file" accept={accept} onChange={onChange} className="hidden" />
    </label>
  );
}
