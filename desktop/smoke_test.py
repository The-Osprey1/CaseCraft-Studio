"""Run the BUILT app's headless self-test and fail loudly if anything is missing from the bundle.

    python desktop/smoke_test.py [dist/CaseCraftStudio/CaseCraftStudio.exe]

The exe is started with --smoke-test in a throw-away data/log folder; it starts the CAD server,
checks presets, the access token, two previews (one with a font-based text pattern), a full
export ZIP and a laser SVG, then exits 0/1. Catches hidden-import and data-file gaps that only
exist in the frozen build.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "CaseCraftStudio" / "CaseCraftStudio.exe"
    if not exe.is_file():
        print(f"FAIL: {exe} not found -- build it first", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="casecraft-smoke-") as tmp:
        out = Path(tmp) / "report.json"
        env = dict(os.environ, CASECRAFT_DATA_DIR=str(Path(tmp) / "data"), CASECRAFT_LOG_DIR=str(Path(tmp) / "logs"))
        env.pop("CASECRAFT_TOKEN", None)
        try:
            proc = subprocess.run([str(exe), "--smoke-test", "--smoke-out", str(out)], env=env,
                                  timeout=900, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print("FAIL: smoke test timed out after 15 minutes", file=sys.stderr)
            return 1
        if not out.is_file():
            print(f"FAIL: no report written (exit code {proc.returncode})", file=sys.stderr)
            log = Path(tmp) / "logs" / "casecraft.log"
            if log.is_file():
                print(log.read_text(encoding="utf-8", errors="replace")[-6000:], file=sys.stderr)
            return 1
        report = json.loads(out.read_text(encoding="utf-8"))
    for r in report["results"]:
        status = "ok  " if r["ok"] else "FAIL"
        extra = r.get("detail") or r.get("error") or ""
        print(f"[{status}] {r['check']:<22} {r.get('seconds', ''):>6}  {extra}")
        if not r["ok"] and r.get("trace"):
            print(r["trace"], file=sys.stderr)
    print(f"Smoke test {'PASSED' if report['ok'] else 'FAILED'} (CaseCraft Studio {report['version']}, "
          f"frozen={report['frozen']}, exit code {proc.returncode})")
    return 0 if report["ok"] and proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
