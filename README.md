# CaseCraft Studio

An open-source, self-hosted parametric B-Rep phone case generator built with **build123d** (OpenCascade), **Shapely**, **FastAPI**, and **React + Three.js (`@react-three/fiber`)**.

Supports both **4-part modular snap-fit printing** (for single-extruder and AMS printers) and **multi-toolhead print-in-place / 1-piece unibody printing** (e.g., H3C tool-changers), plus **1:1 mm laser-ready SVG** outlines.

---

## Core Architecture

### 1. Print Modes & Mechanical Snap-Fit Design
- **4-Part Modular Snap-Fit (`Case_Set.3mf` + individual `.stl`/`.step`):**
  1. **Bumper Frame (`Frame_TPU`):** Back-down support-free geometry with 45° ruled lofts (`offset_frustum`) on both the internal retention groove ceiling and screen-lip underside, port cutouts, and captured button pockets.
  2. **Interchangeable Backplate (`Backplate_PLA`):** Stepped perimeter tongue with 45° inner lead-in chamfer that snaps flush into the TPU groove, optional internal **MagSafe magnet ring pocket** (`54.4 mm` OD / `45.6 mm` ID + bottom alignment tail), and customizable backplate patterns.
  3. **Camera Protection Ring (`CameraRing`):** Bezel-down press-fit ring with corner relief flex slots and a catch bead that locks into the backplate cutout.
  4. **Floating Tactile Buttons (`Buttons`):** Cap-down rigid inserts with an internal retaining flange captured inside the TPU wall pocket.
- **H3C Tool-Changer Print-in-Place (`Toolchanger_InPlace.3mf`):** Co-registers `Frame_TPU` (`extruder="1"`), `Backplate_Base` (`extruder="2"`), optional `Backplate_Inlay` (`extruder="3"`), and captured `Button_*` parts (`extruder="2"`) in a single multi-part assembly sitting flat on `Z=0`, with `CameraRing` placed alongside on the build plate.
- **1-Piece Fused Unibody (`Unibody_OnePiece.stl`):** Single watertight connected solid sitting on `Z=0` for single-material flexible prints.

### 2. Pattern Engine & Laser Export
- **7 Pattern Types:** `solid`, `hex` (Hexagon Mesh), `voronoi` (Voronoi Cells), `waves` (Sine Waves), `grid` (Diamond Grid), `text` (native `build123d` `Text()` monogram), and `svg` (custom `.svg` upload or built-in vector emblems).
- **3 Extrusion Modes:** `through` (open vents), `deboss` (recessed back-face engraving), and `inlay` (2-color flush `.3mf` sub-part insert via `Backplate_Multicolor.3mf`).
- **Auto Stencil Bridges:** Automatically adds `1.4 mm` retaining ribs across interior loops (`O`, `A`, `B`, `D`, `P`, `R`) in `through` mode so letter counters stay anchored.
- **Laser SVG (`Laser_Backplate.svg`):** Clean `1:1 mm` closed paths generated directly from Shapely 2D geometry.

### 3. Built-In Device Library (10 Presets)
Verify dimensions with calipers for your specific device revision:
- Apple: `iphone_15`, `iphone_15_pro`, `iphone_16_pro`, `iphone_16_pro_max`
- Google: `pixel_8_pro`, `pixel_9_pro`, `pixel_9_pro_xl`
- Samsung: `galaxy_s24`, `galaxy_s24_ultra`
- OnePlus: `oneplus_13`

---

## Quick Start

### 1. Install Backend Dependencies
```bash
pip install -r requirements.txt
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
Open `http://127.0.0.1:8000` in your browser.
- **Simple Wizard (Default):** 3-step guided flow (*1. Phone → 2. Style & MagSafe → 3. Calibration, Colors & Export*).
- **Pro CAD Mode:** Unlocks raw caliper dimensions, dynamic button/port editors, clearance sliders, live 2D mechanical cross-section schematics, and `preset.json` import/export.

---

## Headless CLI & Verification

Run the CAD verification suite or generate a 10-minute corner fit-test coupon:

```bash
# Full 4-part + toolchanger + unibody export & geometry/watertight/DFM verification
python cli_test.py --preset iphone_16_pro --pattern voronoi --mode through --magsafe --out out/voronoi

# 10-minute corner fit-test coupon for tolerance calibration
python cli_test.py --preset iphone_15_pro --coupon --out out/coupon

# FastAPI endpoint integration suite
python test_api.py
```

---

## Project Layout
```text
casecraft/
├── cad_engine.py          # build123d B-Rep generators, 2D Shapely patterns, unibody & coupon
├── bambu_3mf.py           # Zero-dependency multi-part/multi-extruder .3mf packager
├── params.py              # Preset dataclasses, derived dims & geometric validation
├── safe_ops.py            # Clamped fillet/chamfer guards for OpenCascade stability
├── dfm.py                 # Overhang/bridge DFM analyzer on Z-up print meshes
├── server.py              # FastAPI API (/presets, /generate-preview, /export-zip, /export-part)
├── cli_test.py            # Headless CAD & DFM verification gate
├── test_api.py            # FastAPI TestClient verification suite
├── presets/               # 10 JSON phone presets
├── schema/                # JSON Schema (draft 2020-12) for phone presets
└── web/                   # React + Vite + Tailwind CSS + @react-three/fiber 3D Studio UI
```
