import { useCallback, useState } from "react";
import { downloadBlob, filenameFrom, postJson } from "../api.js";

/**
 * Export/download actions. Every export regenerates geometry on the server from the CURRENT
 * config + printer profile, and is refused client-side unless the preview for exactly that
 * config is current and free of blocking findings (`canExport`), so a stale or invalid preview
 * is never what the user thinks they downloaded.
 */
export default function useExports({ config, printerId, canExport, onError }) {
  const [exporting, setExporting] = useState(null); // null | 'full' | 'coupon' | part key

  const run = useCallback(
    async (tag, url, fallbackName) => {
      if (!config || !canExport || exporting) return;
      setExporting(tag);
      onError(null);
      try {
        const res = await postJson(url, config);
        downloadBlob(await res.blob(), filenameFrom(res, fallbackName));
      } catch (err) {
        onError(err.message);
      } finally {
        setExporting(null);
      }
    },
    [config, canExport, exporting, onError]
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
