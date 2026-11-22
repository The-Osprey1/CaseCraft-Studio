# CaseCraft Studio

An open-source, self-hosted parametric B-Rep phone case generator built with **build123d** (OpenCascade), **Shapely**, **FastAPI**, and **React + Three.js (`@react-three/fiber`)**.

Supports **4-part modular snap-fit printing** (single-extruder and AMS printers), an **experimental multi-toolhead print-in-place** export (toolchanger printers such as the Bambu Lab H3C), a **1-piece single-material unibody**, and **1:1 mm laser-ready SVG** outlines.

> **What CaseCraft verifies, and what it doesn't.** Every export is checked as *geometrically valid* (OpenCascade solids) and *mesh valid* (watertight, consistently wound, 3MF structure checked independently and by lib3mf). CaseCraft does **not** slice your files and has **not** physically fit-tested any device preset. Every shipped preset is labelled *approximate*. Print a fit-test coupon first. See [docs/MANUFACTURING_VERIFICATION.md](docs/MANUFACTURING_VERIFICATION.md).

---

## Core Architecture

### 1. Print Modes & Mechanical Snap-Fit Design
- **4-Part Modular Snap-Fit (`Case_Set.3mf` + individual `.stl`/`.step`):**
  1. **Bumper Frame (`Frame_TPU`):** printed back-down without supports. 45° ruled lofts (`offset_frustum`) form the retention-groove ceiling and the underside of the screen lip. Port cutouts and captured button pockets are cut into the frame.
  2. **Interchangeable Backplate (`Backplate_PLA`):** a stepped perimeter tongue with a 45° inner lead-in chamfer snaps flush into the TPU groove. Options: an internal **MagSafe magnet-ring pocket** (`54.4 mm` OD / `45.6 mm` ID plus a bottom alignment tail) and backplate patterns.
  3. **Camera Protection Ring (`CameraRing`):** printed bezel-down. It press-fits into the backplate cutout, with corner relief flex slots and a catch bead. Optionally the aperture is **lofted from the camera island's base to a separate outer-opening profile**, for islands wider at the base or flared openings.
  4. **Floating Tactile Buttons (`Buttons`):** cap-down rigid inserts, held by an internal retaining flange captured inside the TPU wall pocket.
- **Toolchanger Print-in-Place (`Toolchanger_InPlace.3mf`) — EXPERIMENTAL, toolchanger printer profiles only:** the frame (`extruder 1`), backplate (`2`), inlay (`3`) and buttons (`2`) are co-registered in their assembled positions. Each export includes `PrintInPlace_Report.txt`, a gap analysis of every co-printed pair. With the default clearances, the backplate sits 0.15 mm from the TPU, and buttons touch their pockets at rest. Those parts will print in contact.
- **1-Piece Unibody (`Unibody_OnePiece.stl`):** one connected solid built from first principles: the bumper envelope with a solid floor. It is verified on every export as one valid, void-free, self-intersection-free solid and a single watertight mesh body. Single-material adaptations are reported, never silent:
  - raised TPU button covers replace the floating buttons
  - the camera surround is flush
  - an inlay becomes a deboss

### 2. Pattern Engine & Laser Export
- **10 Pattern Types:**
  - lattices: `hex`, `dots`, `triangles`, `grid` (diamond grid), `voronoi` (with a seed and relaxation)
  - stripes: `waves` (sine), `chevron` (zig-zag)
  - emblems: `text` (native `build123d` `Text()`, with font, bold and rotation), `svg` (with rotation)
  - `solid`
- **Pattern finishing:**
  - `edge` sets how a lattice meets the border of the patterned area: `clip` (cells cut at the border, the default, so saved designs build unchanged), `whole` (only complete cells, leaving a solid border) or `fade` (cells shrink towards the border over `fade_width` mm).
  - `corner_radius` (0–5 mm) rounds every convex cut-out corner of lattices and stripes. It can only shrink a cut-out, so connectivity can only improve.
- **Instant 2D preview:** all 2D pattern geometry lives in `patterns.py` (Shapely). `/api/pattern-preview` and `/api/pattern-gallery` return back-view SVG paths without waiting for the CAD lock, so the UI shows the cut-out count, open area and connectivity in milliseconds while the 3D model rebuilds. The UI builds its pattern controls from `/api/patterns`.
- **3 Extrusion Modes:**
  - `through`: open vents
  - `deboss`: recessed back-face engraving
  - `inlay`: 2-color flush sub-part, delivered as `Backplate_Multicolor.3mf`
- **Connectivity check:** through-cuts are checked in 2D before any 3D work. A design that would detach material (letter counters, enclosed SVG shapes, lattice strips) is **rejected** with the count, size and location of the loose pieces and how to fix it. Ligaments thinner than one extrusion width are flagged.
- **Auto Stencil Bridges:** `1.4 mm` ribs across interior loops (`O`, `A`, `B`, …) keep letter counters attached.
- **Laser SVG (`Laser_Backplate.svg`):** clean `1:1 mm` closed paths from the Shapely 2D geometry.

### 3. Printer Profiles
Minimal, data-driven profiles live in `printers.py` and are served by `GET /api/printers`. The selected profile drives:
- the print-bed preview
- part placement
- plate-boundary checks
- 3MF filament-slot limits
- whether print-in-place is offered

| Profile | Plate | Print-in-place | Source |
|---|---|---|---|
| `generic_256` (default) | 256 × 256 mm | no | the previous fixed layout bed |
| `bambu_h3c` | 330 × 320 × 325 mm | yes (experimental) | third-party reviews; manufacturer page not retrievable, **unverified** |

The preview and `Case_Set.3mf` use the **same layout**. If the parts don't fit, the preview shows the overflow, and export is blocked with a clear error.

### 4. Fit-Test Coupons
Coupons are trimmed from the real generator geometry, so dimensional relationships are preserved:
- **`camera`** (default, unchanged behavior): the camera ring, the backplate snap joint at the camera corner, and the nearest button.
- **`buttons`**: the real button windows and flange pockets in the bumper wall, the matching backplate edge, and every button.
- **`ports`**: the bottom wall with the real charging and speaker openings, plus the matching backplate edge.

To see the print time, slice the coupon. CaseCraft does not estimate print durations.

### 5. Device Library (10 presets, all *approximate*)
Each preset carries optional `verification` metadata: `level` (`approximate` | `dimensionally_verified` | `physically_fit_tested`), `source`, `fit_test`, `notes` and `unverified_features`. The level is shown beside the selected device. Presets without the block still load.
- Apple: `iphone_15`, `iphone_15_pro`, `iphone_16_pro`, `iphone_16_pro_max`
- Google: `pixel_8_pro`, `pixel_9_pro`, `pixel_9_pro_xl`
- Samsung: `galaxy_s24`, `galaxy_s24_ultra`
- OnePlus: `oneplus_13`

---

## Quick Start

### 1. Install Backend Dependencies (Python 3.12)
```bash
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # + pytest and lib3mf for verification
```

### 2. Build the Frontend (`web/`)
```bash
cd web
npm install
npm run build
cd ..
```

### 3. Start CaseCraft Studio
```bash
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000`.
- **Simple Wizard (Default):** 1. Phone → 2. Style & MagSafe → 3. Printer, Colors & Export.
- **Pro CAD Mode:** raw caliper dimensions (including the optional camera outer opening), button and port editors, clearance sliders, a cross-section diagram, and `preset.json` import/export.
- **Validation status** (header and export step): *Ready to export*, *Warning — review recommended*, *Invalid design — export blocked*, or *Verification pending*. Click it for the concrete findings. Exports are enabled only when the preview matches the current design and printer.

---

## Desktop App (Windows)

`CaseCraftStudio-Setup-<version>.exe` installs CaseCraft Studio as a normal Windows app. It is a per-user install, so it needs no administrator rights. You get a Start-menu entry, an uninstaller and, optionally, `.casecraft` file association. The app opens in its own window using the Microsoft Edge WebView2 runtime, which ships with Windows 11. The CAD engine runs inside the app on a private localhost port, protected by a random per-launch token.

**What the desktop app adds:**
- **Native Save / Open dialogs.** Every export (ZIP, 3MF, STL, SVG, preset JSON) goes to the file you choose, via a temp file that is then moved into place. Exports end with *Show in folder*.
- **Projects (`.casecraft`).** These save the design, printer, colours and coupon type. The file menu next to the device name offers *New*, *Open*, *Save*, *Save as* and a *Recent* list, with shortcuts `Ctrl+N`, `Ctrl+O`, `Ctrl+S` and `Ctrl+Shift+S`. The window title shows unsaved changes, and closing asks first.
- **Autosave and crash recovery.** Unsaved changes are autosaved two seconds after the last edit. After a crash, the next start offers to restore them.
- **My devices.** In Pro mode, use *Save as my device…* to keep your own measured phones beside the built-in presets. They are stored per user and survive updates and reinstalls.
- **Reliability:**
  - a start-up self-check
  - a single running instance, so a second launch or a double-clicked project goes to the open window
  - automatic restart of the CAD engine if it stops
  - a recoverable error screen instead of a blank window
  - rotating logs
  - *Copy diagnostics* in the file menu

| What | Where |
|---|---|
| Program | `%LOCALAPPDATA%\Programs\CaseCraft Studio` |
| Settings, saved devices, autosave | `%APPDATA%\CaseCraft Studio` |
| Logs | `%LOCALAPPDATA%\CaseCraft Studio\logs` |

### Building the installer
You need Python 3.12 with `requirements-desktop.txt` installed, Node 20 or newer, and [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`). Then run:
```powershell
powershell -ExecutionPolicy Bypass -File desktop\build.ps1
```
The script runs these steps and stops at the first failure:
1. Builds the frontend.
2. Runs the fast tests.
3. Runs PyInstaller (`desktop/casecraft.spec`, which produces `dist/CaseCraftStudio/`).
4. Runs `desktop/smoke_test.py` against the built exe. It starts the packaged CAD server headless, then checks the presets, the token, two previews and a full export.
5. Runs Inno Setup (`desktop/installer.iss`, which produces `dist/CaseCraftStudio-Setup-<version>.exe`).

The version lives in `version.py`. To run the desktop shell from source, use `python desktop/app.py`, or add `--debug` for WebView developer tools.

---

## Verification & Tests

```bash
python -m pytest -m "not slow"           # fast: parameter rules, 2D checks, 3MF validator, API errors (~10 s)
python -m pytest                         # full: + B-rep generation, exports, fixtures, coupons (~3 min)

# Headless CLI gate (exit 0 pass, 1 check failed, 2 invalid design)
python cli_test.py --preset iphone_16_pro --pattern voronoi --mode through --magsafe --out out/voronoi
python cli_test.py --preset iphone_15_pro --pattern hex --mode inlay --printer bambu_h3c --out out/h3c
python cli_test.py --preset iphone_15_pro --pattern voronoi --edge fade --corner-radius 1.5 --out out/fade
python cli_test.py --preset iphone_16_pro --coupon --coupon-type buttons --out out/coupon

# Independent 3MF validation (+ lib3mf strict mode when installed)
python verify_3mf.py out/h3c/Toolchanger_InPlace.3mf --printer bambu_h3c
python verify_3mf.py --make-fixtures out/3mf_fixtures     # the 5 reference fixtures
```
GitHub Actions (`.github/workflows/ci.yml`) runs:
- the fast tests
- the slow geometry and export suite, with CLI gates and 3MF fixtures uploaded as artifacts
- the frontend build

---

## Project Layout
```text
casecraft/
├── cad_engine.py          # build123d generators: frame, backplate, ring, buttons, unibody, coupons, export
├── patterns.py            # 2D plate geometry + pattern library (Shapely): cells, edge modes, connectivity, UI previews
├── params.py              # preset dataclasses, derived dims; Preset.check() = the single source of validation rules
├── printers.py            # minimal printer profiles (plate size, slots, toolchanger)
├── bambu_3mf.py           # zero-dependency multi-part/multi-extruder 3MF writer + shared plate layout
├── verify_3mf.py          # independent 3MF validator, lib3mf cross-check, reference fixtures
├── verify.py              # B-rep / mesh checks (one piece, voids, self-intersection, watertight)
├── print_in_place.py      # co-printed part relationships + directional gap probes (experimental)
├── dfm.py                 # overhang/bridge DFM analyzer on Z-up print meshes
├── safe_ops.py            # clamped fillet/chamfer guards for OpenCascade stability
├── server.py              # FastAPI API (/presets, /user-presets, /printers, /patterns, /pattern-preview, /generate-preview, /export-zip, /export-part)
├── appdirs.py             # bundled-resource vs per-user paths (works frozen), atomic writes
├── projects.py            # .casecraft project files + recent list
├── version.py             # single version number
├── desktop/               # Windows app: launcher, JS bridge, PyInstaller spec, installer, build + smoke test
├── cli_test.py            # headless CAD + export verification gate
├── test_*.py              # pytest suites (fast + slow)
├── presets/               # 10 JSON phone presets (approximate)
├── schema/                # JSON Schema (documentation; params.py is authoritative)
├── docs/                  # manufacturing verification guide, implementation report
└── web/                   # React + Vite + Tailwind + @react-three/fiber UI
    └── src/{App.jsx, api.js, constants.jsx, hooks/, components/}
```

## License
No license has been chosen yet; that decision is outstanding with the project owner. Third-party projects consulted as references (not copied) are listed with their licenses in `docs/IMPLEMENTATION_REPORT.md`.
