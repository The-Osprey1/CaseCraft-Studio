import { useCallback, useState } from "react";
import { downloadBlob, filenameFrom, postJson } from "../api.js";
import { IS_DESKTOP, call } from "../desktop.js";

/**
 * Export/download actions. Every export regenerates geometry on the server from the CURRENT
 * config + printer profile, and is refused client-side unless the preview for exactly that
 * config is current and free of blocking findings (`canExport`), so a stale or invalid preview
 * is never what the user thinks they downloaded.
 *
 * Desktop: a native Save As dialog picks the target first, then the app streams the export
 * straight to that file (no large blobs through the web view). Browser: a normal download.
 */
export default function useExports({ config, printerId, canExport, onError, onSaved }) {
  const [exporting, setExporting] = useState(null); // null | 'full' | 'coupon' | part key

  const run = useCallback(
    async (tag, url, fallbackName) => {
      if (!config || !canExport || exporting) return;
      onError(null);
      if (IS_DESKTOP) {
        const target = await call("save_file", fallbackName);
        if (!target.ok) {
          if (!target.cancelled) onError(target.error);
          return;
        }
        setExporting(tag);
        try {
          const [path, query = ""] = url.split("?");
          const endpoint = path.replace(/^\/api\//, "");
          const r = await call("export_to", target.path, endpoint, query, config);
          if (r.ok) onSaved?.(r);
          else onError(r.error);
        } finally {
          setExporting(null);
        }
        return;
      }
      setExporting(tag);
      try {
        const res = await postJson(url, config);
        downloadBlob(await res.blob(), filenameFrom(res, fallbackName));
      } catch (err) {
        onError(err.message);
      } finally {
        setExporting(null);
      }
    },
    [config, canExport, exporting, onError, onSaved]
  );

  const printerQ = `printer=${encodeURIComponent(printerId)}`;
  const exportZip = (coupon = false, couponType = "camera") =>
    run(
      coupon ? "coupon" : "full",
      coupon
        ? `/api/export-zip?coupon=true&coupon_type=${encodeURIComponent(couponType)}&${printerQ}`
        : `/api/export-zip?${printerQ}`,
      coupon ? `${config?.id}_coupon_${couponType}_bundle.zip` : `${config?.id}_casecraft_bundle.zip`
    );
  const exportPart = (partKey, filenameSuffix) =>
    run(partKey, `/api/export-part?part=${partKey}&${printerQ}`, `${config?.id}_${filenameSuffix}`);

  return { exporting, exportZip, exportPart };
}
