# Manufacturing verification

CaseCraft is an engineering tool, so every claim about a part names the level of evidence behind it. The four levels are **not** interchangeable.

| Level | Meaning | Who establishes it | Status in CaseCraft |
|---|---|---|---|
| **Geometrically valid** | The CAD kernel produced valid solids. | Automatic, every export | **Yes**: OpenCascade validity, solid/shell count, self-interference (`verify.py`) |
| **Mesh valid** | The exported mesh is watertight, consistently wound, and one body where one is intended. The 3MF package conforms structurally. | Automatic, every export and CI | **Yes**: trimesh topology, `verify_3mf.py` (independent parser) and lib3mf 2.5.0 strict mode |
| **Slicer verified** | The file was imported **and sliced** in a real slicer, with the expected filament per part. | A person with the slicer | **Not performed.** No file has been opened in Bambu Studio or OrcaSlicer by this project. |
| **Physically verified** | A printed part was fitted to the intended device with the intended materials. | A person with a printer and the phone | **Not performed.** Every shipped preset is `approximate` with fit test `untested`. |

The export README (`README.txt` in every ZIP) repeats this status for the specific design.

## What is checked automatically

- **Parameters** (`params.Preset.check`, the single source of rules for the CLI, API and UI):
  - finite numbers and correct types everywhere
  - clearance limits, plus a recommended tuning range (a warning, not a validated tolerance)
  - wall, groove and rear-lip thickness
  - button pocket height and spacing
  - port positions and overlaps
  - camera island and outer-opening walls and overhang
  - pattern pitch, web width and depth
  - MagSafe floor
- **Through-cut connectivity:** detached regions are rejected before any 3D work, and ligaments thinner than 0.4 mm are flagged.
- **Unibody:** one valid solid, no sealed voids, no self-intersection, and a single watertight mesh body. This is enforced on every export.
- **Plate fit:** parts are laid out on the selected printer's plate. Overflow blocks export, and the preview shows the same layout.
- **3MF:**
  - OPC package and relationships, millimeter units, and declared namespaces
  - core-only build-item attributes
  - oriented 2-manifold meshes with positive volume
  - object, component and build references and cycles
  - identity rotation, with every item resting on Z=0 inside the plate
  - no overlapping items
  - `model_settings.config` objects and parts matching the model, with extruder numbers inside the printer's slot count
- **Registration:** inlay inside its pocket and flush with the outer face. Print-in-place sub-parts keep their design-pose offsets, to within 0.02 mm.
- **Print-in-place gaps** (`print_in_place.py`): each co-printed pair is probed for contact in ±X, ±Y and ±Z at **heuristic** thresholds (0.30 mm sideways; 2 layers, 0.40 mm at a 0.2 mm layer height, vertically). The thresholds come from typical 0.4 mm nozzle behavior. They are not measured CaseCraft data.

## Known print-in-place risks (toolchanger export)

With the default clearances, the gap report finds:
- **Backplate ↔ TPU frame: 0.15 mm in every direction.** The rigid tongue is printed directly on the TPU rear lip, less than one layer above it. The parts will print in contact and may bond. TPU-to-PLA/PETG adhesion varies by brand and settings.
- **Buttons ↔ pockets: zero gap.** At rest, each button's flange bears on its pocket ceiling, so they print fused.
- **Inlay ↔ base:** fused by design (same object, 0.075 mm side gap).
- **Camera ring:** printed beside the case and pressed in afterwards.

Separate meshes do **not** become separate, movable printed parts automatically. Treat `Toolchanger_InPlace.3mf` as an experiment until you have printed it, and record your material pair and clearances.

## Checking the 3MF fixtures in Bambu Studio (manual)

1. Generate the reference files:
   ```bash
   python verify_3mf.py --make-fixtures out/3mf_fixtures
   ```
   This writes five folders, each with its own 3MF files, plus `fixtures_report.json`:
   - `modular_single_material`
   - `multicolor_inlay`
   - `h3c_print_in_place`
   - `multi_button`
   - `magsafe`
2. In Bambu Studio, use **File → Open Project** (or Import 3MF) on each file. When asked about a third-party file, choose to load geometry and part settings.
   - Bambu Studio may not apply assignments written by other software. If it shows a filament or color import dialog, note what it did.
   - OrcaSlicer usually applies embedded settings.
3. For each object, expand the object list and confirm:
   - the parts are listed with their expected names: `Frame_TPU`, `Backplate_Base`, `Backplate_Inlay`, `Button_*` and `CameraRing`
   - each part's **filament number** matches `fixtures_report.json` (for example `Frame_TPU` = 1, `Backplate_Base` = 2, `Backplate_Inlay` = 3)
   - the inlay sits flush in the backplate, and the print-in-place parts are assembled rather than scattered
   - everything sits on the plate, inside the plate boundary
4. Slice. Record any errors or warnings, plus the time and filament estimate, then inspect the first layers in the preview.
5. Record the result (slicer name and version, file, pass/fail, notes). Until someone does this, describe the files as *mesh valid*, not *slicer verified*.

## Manual checklist for a real Bambu Lab H3C

Before starting, confirm the H3C profile's plate size (330 × 320 mm, taken from reviews) against your printer or Bambu's spec sheet.

**1. Fit coupon first** (≈ material for a few small parts):
- [ ] Export the **Camera & Snap** coupon (Wizard step 3 → coupon type → Download, or `--coupon`).
- [ ] Slice it. Print the frame piece in TPU and the backplate and ring in your rigid filament.
- [ ] Snap the backplate segment into the frame groove. Record whether it is too loose, right, or too tight, and how much force removal takes.
- [ ] Press in the camera ring. Check that it seats, holds, and clears the camera bump on the real phone.
- [ ] Repeat with the **Buttons** and **Bottom Ports** coupons. Check that the button windows and port openings line up with the real phone.
- [ ] Adjust the clearances (Pro → Tolerances) and re-print until the coupons fit. Note the values.

**2. Modular print** (`Case_Set.3mf`, generic or H3C profile):
- [ ] Open in Bambu Studio and check the filament per part (frame TPU, backplate and ring rigid) and plate placement. Slice.
- [ ] Print. Fit the frame to the phone, then snap in the backplate, the camera ring and the buttons.
- [ ] Check the screen lip, port access, button actuation, MagSafe charging (if used) and the camera field of view (including ultra-wide vignetting).
- [ ] Record the device, preset version, clearances, materials and results.

**3. Print-in-place experiment** (`Toolchanger_InPlace.3mf`, H3C profile, **experimental**):
- [ ] Read `PrintInPlace_Report.txt` in the export. Expect the backplate and buttons to print in contact with the TPU.
- [ ] Open in Bambu Studio and confirm the toolhead per part (frame 1, backplate 2, inlay 3, buttons 2). Slice. Check the TPU/rigid interface layers in the preview.
- [ ] Print. Try to separate the backplate from the frame by flexing the TPU, and try each button.
- [ ] Record the material pair, nozzle and layer height, whether parts bonded, and whether they separate without damage. Only after a documented pass should a clearance profile be called validated.

**4. Update the preset only with evidence:**
- [ ] After measuring with calipers, set the preset's `verification.level` to `dimensionally_verified`, with `source` describing how you measured.
- [ ] After a passing physical fit, set it to `physically_fit_tested` with `fit_test: "passed"` and notes (material, clearances, date).
