# CaseCraft Studio: reliability implementation report

Branch: `feature/reliability-improvements`, from `fix/review-bugs` at `30722fd`. Not merged into `main`.

## Baseline (before any change)

The environment used for all baseline and final runs:
- Windows 11, Python 3.12 (the Anaconda interpreter lacks build123d)
- build123d 0.13.0, shapely 2.1.2, fastapi 0.163.2, trimesh 5.1.1, numpy 2.5.3, lib3mf 2.5.0
- Node 26.13.1, Vite 6.4.6

| Suite | Result | Time |
|---|---|---|
| `test_regressions.py` | 11/11 pass | 12.8 s |
| `test_api.py` | all pass | 61.5 s |
| `cli_test.py` voronoi + MagSafe, iPhone 16 Pro | 55/55 | 14.0 s |
| `cli_test.py` hex inlay, iPhone 15 Pro | 62/62 | 15.6 s |
| `cli_test.py --coupon` | 25/25 | 5.1 s |
| `npm run build` | builds (1.1 MB bundle warning) | 2.9 s |

**Baseline preview timings** (hex through): frame 0.40 s, backplate 0.83 s, ring 0.15 s, buttons 0.07 s. The text inlay backplate took 2.0 s.

**Pre-existing failures:** none in the existing suites. Issues present before this work but not caught by those suites, found while working:
- **Every 3MF failed lib3mf strict mode.** The `BambuStudio:` metadata prefix was undeclared, and build items carried the non-core `printable` attribute.
- **Unibody fused separately-toleranced parts.** Each part used a −0.05 mm clearance hack, and sealed voids were stripped by keeping the largest shell.
  - It was flush at the camera.
  - It kept empty inlay pockets without telling anyone.
  - It fused floating buttons, flange voids included.
- **Through-cut islands only logged a warning.** They were still exported.
- **The waves pattern left ~0.1 mm ribs at default settings.** Slots were sized from the vertical pitch, not the perpendicular rib width.
- **The preview fell back to a 600 mm bed while export used 256 mm.** The two could disagree.
- **Print-in-place parts are co-printed in contact.** The backplate tongue sits 0.15 mm above the TPU rear lip, and buttons rest on their pocket ceilings. Nothing reported this.

## A. Implementation summary

### Milestone A: geometry integrity
- **Unibody rebuilt from first principles** (`generate_unibody`): the bumper envelope with a solid floor, phone cavity, screen lip, ports and camera aperture, so there is no fusing of toleranced parts.
  - **Single-material adaptations:** floating buttons become raised TPU covers with a 45° chamfered underside and an inner press nub. The camera surround is flush, because a raised bezel would lift the case off the bed. An inlay becomes a deboss.
  - **Reporting:** each adaptation is listed by `unibody_adaptations()` in the preview and the export README.
  - **Export guard:** `print_ready_unibody()` asserts one valid solid, one shell (no voids), no self-intersection, and one watertight mesh body.
  - **Modular generators:** they share helpers with the unibody but are otherwise unchanged. A test checks that their volumes did not change.
- **Through-cut connectivity** (`through_cut_connectivity`): shapely computes the material left after the cut. Extra regions are detached solids; holes are openings. A failing design is rejected (ParamError, which becomes HTTP 422 or CLI exit 2) before any 3D work, with:
  - the count, the largest area, and its location
  - a fix tailored to the pattern type
  Thin ligaments (< 0.4 mm) are detected by erosion. Stencil bridges are preserved, and the 3D backstop now raises instead of warning.
- **Waves pattern:** slot width now uses cos(steepest slope), so ribs honor the web width. Steep waves that would leave < 0.4 mm ribs are rejected; narrower-than-web ribs produce a warning.
- **Validation** (`Preset.check` → errors and warnings; `validate()` raises):
  - type and finite checks on every field
  - clearance hard limits (matching the schema) plus a recommended tuning range (warning only)
  - wall behind the groove, rear-lip thickness and front-lip land
  - button-pocket height against the wall, and pocket overlap or close spacing
  - ports past the edge, into a corner (warning), into the lip, overlapping each other (warning) or overlapping buttons
  - camera opening walls and overhang, and the existing pattern rules
  One source serves the CLI, the API and the UI.

### Milestone B: printer-aware geometry and export
- **`printers.py`:** `generic_256` (the default, matching the old behavior) and `bambu_h3c`. The H3C is 330 × 320 × 325 mm with 9 tool heads, per third-party reviews; the bambulab.com spec page returned HTTP 403, so the profile is marked `verified: false` with its source. No per-printer clearances were added, because there is no data to justify them.
- **One layout:** `bambu_3mf.layout_for_printer` lays out both the preview bed and `Case_Set.3mf`. The 600 mm fallback is gone.
  - On overflow, the preview still renders the layout so the problem is visible, adds an error finding and sets `export_blocked`. Exports return 422 (`BedOverflow`).
  - The viewport draws the selected plate, in red on overflow.
  - Endpoints take `?printer=`, and caches key on it. A new `GET /api/printers` endpoint lists the profiles.
- **3MF writer fixes:** the namespace is declared and the vendor attribute is dropped. Filament slots are checked against the printer, and print-in-place is refused for non-toolchanger profiles.
- **`verify_3mf.py`:** an independent validator (it shares no code with the writer), plus `lib3mf` strict mode when installed, plus five reference fixtures (`--make-fixtures`). Lib3MF is used only in tests and CI, as an optional dev dependency.
- **`print_in_place.py`:** classifies each co-printed pair as captured, moving, fused or post-assembly. It reports intersecting, touching, below-printable gap, or printable gap, using exact B-rep shift probes. The preview uses analytic quick findings, and a test checks they agree with the full probe. The export includes `PrintInPlace_Report.txt`, and the UI labels the mode experimental.
- **Export README:** a `README.txt` in every ZIP states the verification level of each claim.
- **Server:** the preview endpoint skips CAD work for requests the browser has already abandoned, so superseded previews no longer hold up the serialized CAD lock.

### Milestone C: fit and device modeling
- **Coupons** (`generate_test_coupon(p, coupon_type)`), all trimmed from real generator geometry:
  - `camera`: the default, unchanged.
  - `buttons`: the real windows and pockets, the backplate edge, and all buttons.
  - `ports`: the bottom wall openings and the backplate edge.
  Available via CLI `--coupon-type`, API `coupon_type=`, and the Wizard step 3 selector. The "10-minute" claims were removed.
- **Preset `verification` metadata:** level, source, fit_test, notes and unverified_features. All 10 presets are honestly `approximate` and `untested`, with origin "not recorded". It is backward compatible.
- **Optional `camera.opening`:** a clear aperture at the outer face, ruled-lofted from the island base, with a back-view offset for asymmetric bumps. It is validated for flange and spigot walls, radius and 45° overhang. Existing presets build identically, which a test checks.
- **JSON schema:** documents the new fields, and a test keeps it in sync with `params.py`.

### Milestone D: frontend and quality
- **App.jsx refactor:** reduced from 2,343 to about 1,600 lines. Extracted:
  - `constants.jsx`
  - `components/Fields.jsx` and `PatternControls.jsx`
  - `api.js`
  - `hooks/usePreview.js` and `hooks/useExports.js`
  - `components/ValidationStatus.jsx`, `DeviceBadge.jsx` and `PrinterSelect.jsx`
  No new libraries, and the layout and styling are preserved.
- **Preview requests:**
  - superseded requests are aborted (AbortController)
  - every result is keyed to its exact config and printer
  - a small client LRU cache sits alongside the existing server cache
  - export buttons and the laser-SVG download are enabled only when the preview is current and not blocked
  - changing the printer invalidates the preview, since it is part of the key
- **Validation status:** *Ready to export*, *Warning — review recommended*, *Invalid design — export blocked*, *Verification pending*, plus *Checking…*. Clicking it lists the concrete findings.
- **Verification badge:** shown beside the selected device and on the device cards.
- **Printer selector:** in the header and in Wizard step 3. The toolchanger card is gated by the printer and labelled experimental, with the unibody notes listed.
- **CI:** `.github/workflows/ci.yml` has three jobs:
  - fast tests
  - slow geometry and export tests, CLI gates and fixtures, with artifacts uploaded
  - the frontend build
- **Dependencies:** constrained ranges in `requirements.txt`; `requirements-dev.txt` adds pytest, lib3mf and lxml (needed by trimesh's 3MF reader in `cli_test.py`).

### Milestone E: Windows desktop app (v1.1.0)
- **Packaging:** a PyInstaller one-folder build (`desktop/casecraft.spec`, 475 MB unpacked), wrapped in a per-user Inno Setup installer (`desktop/installer.iss`, about 133 MB). The installer needs no admin rights. It adds a Start-menu entry and an uninstaller, and optionally associates `.casecraft` files. It checks for WebView2, and the uninstaller asks before deleting user data. `desktop/build.ps1` runs these steps and stops at the first failure:
  1. frontend build
  2. fast tests
  3. PyInstaller
  4. frozen smoke test
  5. installer
- **Shell (`desktop/app.py`):**
  - a pywebview (Edge WebView2) window
  - a start-up self-check
  - a single-instance mutex, plus an authenticated localhost hand-off that brings the window forward and forwards the project to open
  - a WebView2-missing check
  - the CAD server on a free port, with a per-launch token and a watchdog restart
  - rotating logs and global exception hooks
  - window geometry kept on a monitor that exists
- **Bridge (`desktop/desktop_bridge.py`):** native Save, Open and confirm dialogs. Exports stream straight to a temp file and are then moved into place. Writes are only allowed to paths the user picked in this session. It also provides projects, the recent list, autosave and restore, and diagnostics.
- **Server:**
  - `appdirs` resource and user paths, so the server works when frozen
  - a bad preset file is skipped, not fatal
  - a user device library (`/api/user-presets`) with id and traversal checks
  - a token middleware, used in desktop mode only
  - a 10 MB request cap
  - a byte-capped export cache
  - error ids on 500s
- **Bugs found by the new tests and manual checks:**
  - `Preset.from_dict([])` silently built a default "Custom" phone; it now raises `ParamError`.
  - The window opened off-screen on first launch under 188 % display scaling, because pywebview's `CenterScreen` is wrong under DPI scaling. The position is now always explicit and checked against the monitors.
  - Confirm dialogs read "127.0.0.1 says"; they are now native.

### Milestone F: pattern library
- **2D geometry split out:** all planar geometry (plate outline, camera cut-out, MagSafe ring and pocket, pattern cells, connectivity) moved from `cad_engine.py` to a new `patterns.py`. `cad_engine.py` re-exports the moved names, so the server, tests and CLI are unchanged.
- **New pattern types:**
  - `dots`: exact circles
  - `triangles`: a triangular lattice with an angle
  - `chevron`: zig-zag stripes. Its rib check shares the waves rule through `stripe_cos()`, using the constant zig-zag slope (4A/L) in place of the sine's steepest slope.
  - `voronoi` gained `seed` and `relax`; `text` and `svg` gained `rotation`.
- **Pattern finishing:** `pattern.edge` (`clip` | `whole` | `fade`), `pattern.corner_radius` (0–5 mm) and `pattern.fade_width` (2–60 mm), validated in `params.py` and the JSON schema.
  - `clip` stays the default, so saved designs build exactly as before.
  - `fade` shrinks cells with a smoothstep down to 25 % of full size. Faded cells under 2 mm² are dropped, because they would close up on an FDM print.
  - `corner_radius` is a morphological opening, so a cut-out can only shrink and connectivity can only improve.
- **Instant 2D feedback:** `GET /api/patterns` returns generator metadata (types, defaults, control ranges, border modes, fonts). `POST /api/pattern-preview` and `/api/pattern-gallery` return back-view SVG path data. These endpoints do not take the CAD lock, so they answer in milliseconds during a 3D rebuild.
- **Frontend:**
  - `PatternControls.jsx` was rewritten to render its controls from `/api/patterns` instead of hard-coded lists.
  - New components: `PatternPreviewCard` (live 2D back view with cut-out count, open area and the connectivity verdict), `PlatePreview` and `ViewportToolbar`.
  - New hooks: `usePatternSpecs`, `usePatternRequest`.
  - `Viewport3D` is now lazy-loaded. Three.js sits in its own ~900 kB chunk, and the entry chunk is ~245 kB.
- **CLI:** `cli_test.py` gained `--edge` and `--corner-radius`, and validates the design before building, so an invalid combination exits 2.
- **Tests:** a new `test_patterns.py` covers the generators, edge modes, corner rounding, previews and the new parameter rules. `test_geometry.py` gained B-rep checks for the new options.

**Milestone F results** (2026-11-22, Windows 11, Python 3.12):

| Command | Result |
|---|---|
| `python -m pytest` | **206 passed**, 0 failed, 0 skipped (3 m 57 s) |
| `cli_test.py --pattern dots --mode through` | **54/54**; backplate 1.21 s |
| `cli_test.py --pattern triangles --mode through --magsafe` | **54/54**; backplate 1.24 s |
| `cli_test.py --pattern chevron --mode through` | **54/54**; backplate 0.38 s |
| `cli_test.py --pattern chevron --mode deboss` | **54/54**; backplate 0.29 s |
| `cli_test.py --pattern hex --mode through --edge whole` | **54/54**; backplate 0.69 s |
| `cli_test.py --pattern voronoi --mode through --edge fade --corner-radius 1.5` | **54/54**; backplate 0.82 s |
| `cli_test.py --pattern grid --mode inlay --edge fade --printer bambu_h3c` | **70/70**, including the multicolor and toolchanger 3MFs; backplate 0.57 s |
| `cli_test.py --pattern hex --mode through` (regression check of the default) | **58/58**; backplate 0.81 s. The 4 extra checks come from the previous run's `Backplate_Multicolor.3mf`, still in the shared `--out` folder and validated too. |
| `cd web && npm run build` | builds with no chunk warning (entry 245 kB; lazy 3D chunk 901 kB, under the raised 1000 kB limit) |
| Manual UI check (built app on uvicorn, in-app browser) | see below |

All CLI runs used the default `iphone_15_pro` preset and printer unless stated.

The manual UI check confirmed:
- the pattern gallery shows all ten types with thumbnails
- choosing Chevron updates the 2D card at once (27 cut-outs, 60.5 % open, "Prints as one piece"), and the rebuilt 3D back view matches it
- on Hexagon, switching the border to Fade shows the fade-distance slider, and the 2D card and 3D model both update (115 → 103 cut-outs, 55.7 % → 34.1 % open)
- there were no console errors and no server errors

Note: `dots` and `triangles` backplates take ~1.2 s, the slowest lattices and closest to the 1.5 s local timing budget.

### Milestone G: iPhone 17 family, brand-first device picker, device editor, preview speed
- **iPhone 17, 17 Pro, 17 Pro Max and Air presets** from Apple's accessory dimensional drawings (dated 2025-09-09):
  - Labelled dimensions give the body, button and port positions and the MagSafe centre (the Apple logo).
  - The camera plateau extents were scaled off the drawings' vector geometry at 2.074 pt/mm. Checked against Apple's labelled lens positions, the error is under 0.2 mm.
  - The presets are `dimensionally_verified`, with `camera` listed as unverified, and `fit_test: untested`.
  - Camera Control is an opening, as Apple's guidelines require of cases that don't use Apple's Camera Control interface.
  - On the 5.64 mm Air, the USB-C opening is capped at 5.2 mm. Apple's 6.6 mm keep-out is taller than the side wall allows.
- **Open camera cut-out (`camera.ring: false`):** the 17 Pro, Pro Max and Air have a full-width plateau 2.55–3.03 mm proud of the back glass, more than the 1.8 mm backplate. The iPhone 17's island sits 1.18 mm from the edge. Neither leaves room for the press-fit ring. With the open mode:
  - the backplate clears the island by `camera_aperture_margin + camera_ring_clearance`
  - any plate strip under 3 mm left beside the cut-out is removed (a morphological opening), so the cut-out opens through the edge with no slivers
  - no ring part is made; preview, exports, 3MF writers, print-in-place, coupons, unibody and CLI all handle its absence
  - the frame needs no change: its rear lip sits outside the phone outline (offset ≥ 0.55 mm), so the plateau passes between the walls
  - validation keeps the island within the outline and requires it to cover no more than half the back; the ring rules now point to the open mode
- **Brand-first device picker:** presets carry `brand` and `year`. The wizard shows makers first, then that maker's models newest first, with a search across makers. Pro mode groups the device list by maker.
- **Device editor** (Pro mode, *Device* tab, moved out of `App.jsx` into `DeviceEditor.jsx`):
  - a live front/back sketch (`DeviceDiagram.jsx`) that highlights the field in focus
  - model name, maker and year
  - camera mount choice
  - the previously missing port corner radius and height offset
  - a measurement-provenance section
  - CAD validation problems listed at the top
- **Number fields (`Fields.jsx`)** previously reset on any non-number, so a negative port centre could not be typed, and every keystroke went to the CAD engine. They now:
  - keep the text as typed
  - commit only valid, in-range values
  - flag problems inline
  - support Enter, Escape and the arrow keys
  The preview key also leaves out name, maker, year and provenance, so renaming a device no longer rebuilds the CAD model.
- **Tolerance sliders** offer only values the engine accepts together with the rest of the design (`fitLimits.js`, mirroring the `params.py` rules). Before, a 1.4 mm wall, a 2.0 mm screen lip or a 1.2 mm groove went straight to "invalid design".
- **Preview pipeline:**
  - The frame, camera ring and buttons are memoised on exactly the parameters they read (`cad_engine.part_key`).
  - Each part is meshed once, at 0.05 mm / 0.3 rad. Meshes are read straight into numpy (`dfm.tessellate`), giving the same triangulation as build123d 2–3× faster.
  - Meshes are sent as indexed little-endian arrays instead of two base64 STLs per part. The bed view places parts by offset, so they aren't meshed again, and buttons carry their own small bed mesh.
  - The Case_Set layout is computed from those meshes (`bambu_3mf.set_objects_from_meshes`, same objects and packing).
  - B-rep cut tools follow the 2D outlines within 0.02 mm (`CUT_TOL`); the 2D geometry, checks, preview and laser SVG are unchanged.
  - An untrimmed MagSafe pocket is cut with true circles: 53 plate faces instead of 435, and the same volume within 0.02 %. MagSafe backplates build in 0.6–1.1 s instead of 1.0–1.6 s.
- **Fixes found while doing this:**
  - MagSafe failed in every mode on the Galaxy S24, S24 Ultra and OnePlus 13: the centred ring hit the camera. Each preset now ships with the ring shifted just clear (−3, −5, −11 mm).
  - The Galaxy S24's approximate speaker opening ran 27 mm into a corner whose straight edge ends at 23.3 mm. The cutter sliced obliquely through the curved wall and left a 2 mm unsupported roof, so the frame failed the support-free check (this already failed before G). It is now 10 mm wide at 18 mm, and the warning explains the consequence.
  - `Preset.from_dict` now rejects non-list `buttons`/`ports` and non-object sections with a clear message instead of a type error. It also checks the top-level `id`/`name`/`brand`/`year` types.
  - Small UI fixes:
    - the laser SVG skips non-polygon fragments
    - the sticky pattern card is compact on short windows
    - the camera cut-out shows as an opening in the 2D previews
    - the Camera Ring pill and export appear only when there is a ring

**Preview timings** (`_build_preview`, iPhone 15 Pro unless noted; Windows 11, Python 3.12):

| Design | Before G | After G, first build | After G, pattern change | Payload before → after |
|---|---|---|---|---|
| hex, through | 4.37 s | 1.96 s | 1.08 s | 5.37 → 0.32 MB |
| text, through | 9.80 s | 2.35 s | 0.61 s | 5.90 → 0.25 MB |
| dots, inlay | 11.42 s | 2.43 s | 1.54 s | 26.23 → 1.60 MB |
| iPhone 17 Pro, hex, through | — | 1.60 s | 0.86 s | 0.24 MB |

The "pattern change" column is a rebuild with the frame, ring and buttons cached, as when only the pattern changes in the UI.

**Sweep:** every preset × pattern type × mode × border × MagSafe on/off (1,160 validation and 2D variants) found only the MagSafe clash above, before the fix. A full 3D sweep (13 designs per preset: preview, unibody, three coupons) found no CAD errors. After the fixes, the four new presets plus the three MagSafe presets and the default show zero problems.

**Milestone G results** (2026-11-22, Windows 11, Python 3.12):

| Command | Result |
|---|---|
| `python -m pytest` | **220 passed**, 0 failed, 0 skipped (2 m 57 s) |
| `cli_test.py --preset iphone_17_pro --pattern hex --mode through` | **49/49** (open cut-out: no ring, plate one piece, plateau footprint clear of plate and frame) |
| `cli_test.py --preset iphone_17_pro_max --pattern text --mode inlay --printer bambu_h3c` | **64/64** |
| `cli_test.py --preset iphone_air --pattern solid --mode through --magsafe` | **48/48** |
| `cli_test.py --preset iphone_17 --pattern voronoi --mode through --magsafe` | **49/49**; backplate 1.03 s |
| `cli_test.py --preset galaxy_s24 --pattern hex --mode through --magsafe` | **50/50** (support-free frame after the speaker fix; failed before G) |
| `cli_test.py --preset oneplus_13 --pattern waves --mode deboss --magsafe` | **52/52**; backplate 1.08 s (1.64 s before the exact MagSafe cutter) |
| `cli_test.py --preset iphone_16_pro --pattern voronoi --mode through --magsafe` | **56/56**; backplate 0.62 s |
| `cli_test.py --preset iphone_15_pro --pattern hex --mode through` | **54/54** (ring mode unchanged) |
| `cli_test.py --coupon`: `iphone_17_pro` camera, `iphone_air` ports, `iphone_17` buttons | **22/22**, **17/17**, **47/47** |
| Tolerance slider ranges (`fitLimits.js`) | all 252 endpoints (14 presets × 9 sliders × min/max) pass `Preset.check()` |
| `cd web && npm run build` | builds; entry chunk 259 kB, lazy 3D chunk 898 kB |

The browser check (built app on uvicorn, in-app browser) confirmed:
- **Picker:** makers first (Apple 8, Google 3, Samsung 2, OnePlus 1), Apple's 2025 models first, then their models; Pro mode lists devices grouped by maker.
- **iPhone 17 Pro and Pro Max:**
  - the back view shows the backplate stopping below the open plateau, with no Camera Ring part
  - a hex pattern stays clear of the plateau (125 cut-outs, "Prints as one piece")
  - a pattern change rebuilt with the frame cached ("frame 0s · plate 0.91s · mesh 0.10s")
- **Device editor:**
  - the sketch matches the drawing values (Camera Control centred 98.4 mm from the top)
  - typing "1" into the length shows "Minimum 80 mm" and isn't sent; "152.5" commits; a negative port centre can be typed and commits on Enter
  - the focused port is highlighted on the sketch
  - switching the 17 Pro to a press-fit ring lists the validation message, which points to the open cut-out
- **Tolerances:** sliders show the accepted ranges (wall 1.55–2.4 mm, groove 0.65–0.95 mm, lip 0.6–1.5 mm).
- **Errors:** no console errors besides the deliberate 422 above; no server errors.

### Milestone H: grip and openings (port chamfers, grip grooves, flexible unibody buttons, lanyard pocket)
All four features are built in the CAD engine, validated in `Preset.check()`, documented in the schema and exposed in the UI. Each prints back-down (frame, unibody) or outer face down (backplate) without support, and is checked by the existing overhang gate (`dfm.classify`).

- **Port chamfer / finger scoop** (`style.port_chamfer`, default 0.6 mm, 0–1.2 mm; `ports[].chamfer` overrides it per opening up to 1.5 mm, or `null` for the default):
  - `Preset.port_flare()` gives the flare: it starts `c` mm inside the outer face, opens sideways at 45°, upwards at 1.04 mm per mm (a little steeper than 45°, so the roof is never an overhang) and downwards only as far as keeps ≥ 0.6 mm of wall above the backplate groove and clear of the bed rim. On the shipped presets the small speaker and microphone openings flare fully downwards; most USB-C openings sit close to the groove and get a flat bottom (no downward flare), the 17 Pro Max's a partial one.
  - The cutter is a ruled loft between two rounded rectangles (`_port_local`), used by the frame, the unibody and the ports coupon.
  - New rules: the flare may not climb into the rounded screen-lip rim, and it may not run into a button pocket on the same side.
  - **Behaviour change:** the 0.6 mm default flares every port on existing designs and presets. Set `port_chamfer` to 0 for the old straight openings.
- **Grip grooves** (`style.grip_ribs`, off by default; `grip_rib_depth` 0.2–0.6 mm):
  - Horizontal V-grooves laid out by `grip_rib_layout()` between 1 mm above the backplate joint and 0.5 mm below the screen-lip ramp. The lower flank faces up; the upper flank rises 1.04 mm per mm, so neither needs support.
  - Cut only on the straight part of the left and right walls (`grip_rib_spans`), stopping 1 mm before the corners and keeping 1 mm of whole wall around every button pocket, unibody button cover and flex slit, and port flare. Pieces shorter than 3 mm are left out.
  - New rule: the groove must leave ≥ 0.6 mm of wall behind it. If the wall is too short for any groove, a warning says none are added.
- **Flexible unibody buttons** (`style.compliant_buttons`, on by default; unibody only):
  - Two 0.6 mm through-wall slits flank each button cover, reaching 1 mm above and below it and staying ≥ 0.6 mm clear of the floor and the screen-lip ramp. The wall strip between them stays joined top and bottom and bends like a short beam. Each slit ends in a pointed roof, so it prints without support.
  - Reported in `unibody_adaptations()` either way (slits, or "closed wall, firmer press").
  - How much easier the press actually is has not been measured; it needs a physical print.
- **Lanyard tether pocket** (`style.lanyard_pocket`, off by default; `lanyard_depth` 0.4–0.9 mm):
  - `patterns.lanyard_pocket_poly()` (from the groundwork) is cut into the backplate's inner face, with the neck ending at the plate body edge, and into the unibody floor, with the neck ending at the cavity wall, so the strap lies flush until it leaves through the charging port.
  - It is a pattern keep-out (`pattern_region`), raises a clear error when it would hit the MagSafe ring or the camera cut-out, and is drawn as a dashed outline in the 2D previews. The 2D preview also reports the MagSafe clash for a solid plate.
  - A preview finding explains it, including that the flat laser-cut backplate drawing cannot contain a recess.
- **Preview speed and caching:** `part_key` now leaves `lanyard_*` and `compliant_buttons` out of the frame key, and all Milestone H keys (plus `magsafe_*`) out of the camera ring and buttons keys. Toggling the lanyard pocket or the flexible buttons reuses the cached frame; port chamfer and grip changes rebuild only the frame.
- **Schema:** `style` is now fully documented: all 26 keys with type, default and hard bounds, and `additionalProperties: false` (the parameter loader already rejected unknown keys). A test keeps it in step with `params.Style`.
- **UI:**
  - Pro › Tolerances has a new *Grip & Openings* section (`ErgonomicsControls.jsx`): port chamfer slider, grip grooves toggle and depth, flexible unibody buttons toggle.
  - The pattern panel (wizard and Pro) has a *Lanyard tether pocket* toggle, with the depth slider in Pro mode; the pocket shows as a dashed amber outline on the live back view.
  - Device editor: each port has an *Outer chamfer* field that starts on "Case default" and can be given its own value or reset.
  - `fitLimits.js` bounds the new sliders (rim room for the chamfer, wall for the grooves, plate floor for the pocket) and tightens the wall and backplate sliders when grooves or the pocket are on.

**Milestone H results** (2026-11-27, Windows 11, Python 3.12):

| Command | Result |
|---|---|
| `python -m pytest` | **265 passed**, 0 failed, 0 skipped (3 m 21 s); 45 of them new in `test_ergonomics.py` |
| Every shipped preset with grip grooves and the lanyard pocket on | all 14 validate; frame, backplate and unibody build as one valid solid each, with 0 broad overhangs |
| New slider ranges (`fitLimits.js`) | all 84 endpoints (14 presets × 3 sliders × min/max, features on) pass `Preset.check()` |
| `cli_test.py --preset iphone_16_pro --pattern voronoi --mode through --magsafe` | **56/56** |
| `cli_test.py --preset iphone_17_pro --pattern hex --mode through` | **49/49** |
| `cli_test.py --preset iphone_16_pro --pattern hex --mode through --grip-ribs --lanyard` | **56/56**; backplate 0.81 s |
| `cli_test.py --preset iphone_17_pro_max --pattern text --mode inlay --printer bambu_h3c --grip-ribs --lanyard` | **64/64** |
| `cli_test.py --preset galaxy_s24_ultra --pattern dots --mode deboss --grip-ribs --lanyard --port-chamfer 1.2` | **50/50** on the rerun (backplate 1.36 s). The first run failed the 1.5 s timing check at 1.73 s while the machine was otherwise busy; the same design without the new features takes 1.44 s, so this design sits close to the budget regardless of Milestone H. |
| `cli_test.py --preset iphone_air --pattern solid --mode through --magsafe --grip-ribs --lanyard` | **48/48** (MagSafe ring and lanyard pocket together) |
| `cli_test.py --coupon`: camera (default), `iphone_16_pro` buttons, `iphone_17` ports | **27/27**, **52/52**, **17/17** |
| `cd web && npm run build` | builds; entry chunk 264 kB, lazy 3D chunk 898 kB |
| `desktop\build.ps1` | frontend build, 195 fast tests passed, PyInstaller, packaged-app smoke test all ok (14 presets, previews, export ZIP, laser SVG), `dist\CaseCraftStudio-Setup-1.1.0.exe` (133 MB). Version left at 1.1.0. |

`cli_test.py` gained `--grip-ribs`, `--lanyard` and `--port-chamfer` so the gates can exercise the new features.

The browser check (built app on uvicorn, in-app browser, iPhone 15 Pro) confirmed: the *Grip & Openings* controls appear under Tolerances and turning grip grooves on rebuilds the frame with visible grooves on the side walls; with the lanyard pocket on, a hex pattern stays off the bottom of the plate and the live back view draws the pocket as a dashed outline; each port in the Device tab shows "Case default (0.6 mm) · set own"; no console errors.

**Not verified:** no physical print or slicer import of any Milestone H feature. How much the flex slits soften a button press, how the grip grooves feel, and whether a real lanyard card fits the pocket are all untested.

## B. File-level change summary

**Modified:**
- `cad_engine.py`: unibody, connectivity, waves, frame helpers, `build_case_parts`, export, coupons, camera aperture loft
- `params.py`: `check()`/warnings, type checks, combined rules, `Verification`, `CameraOpening`
- `bambu_3mf.py`: printer layout, `BedOverflow`, slot checks, spec fixes
- `server.py`: printer parameter, findings, bed, README, single-part fast path, `/printers`, abandoned-request skip
- `cli_test.py`: `--printer`, `--coupon-type`, 3MF validation, exit code 2
- `test_api.py`: pytest conversion and new cases
- `presets/*.json` (all 10): verification block
- `schema/phone_preset.schema.json`
- `README.md`, `requirements.txt`
- `web/src/App.jsx`, `web/src/components/Viewport3D.jsx`

**Created:**
- Python: `printers.py`, `verify.py`, `verify_3mf.py`, `print_in_place.py`
- Tests and config: `test_validation.py`, `test_geometry.py`, `test_3mf_validator.py`, `test_printer_export.py`, `pytest.ini`, `requirements-dev.txt`
- CI and docs: `.github/workflows/ci.yml`, `docs/MANUFACTURING_VERIFICATION.md`, `docs/IMPLEMENTATION_REPORT.md`
- Frontend: `web/src/api.js`, `web/src/constants.jsx`, `web/src/hooks/usePreview.js`, `web/src/hooks/useExports.js`, `web/src/components/{Fields,PatternControls,ValidationStatus,DeviceBadge,PrinterSelect}.jsx`

**Removed:** none. `test_regressions.py` and `dfm.py`/`safe_ops.py` are unchanged; `CrossSectionDiagram.jsx` is unchanged.

**Milestone F:**
- Created: `patterns.py`, `test_patterns.py`, `web/src/hooks/{usePatternSpecs,usePatternRequest}.js`, `web/src/components/{PatternPreviewCard,PlatePreview,ViewportToolbar}.jsx`
- Modified: `cad_engine.py` (2D code moved out), `params.py`, `schema/phone_preset.schema.json`, `server.py`, `cli_test.py`, `test_geometry.py`, `web/src/{App,constants}.jsx`, `web/src/components/{Fields,PatternControls,Viewport3D}.jsx`, `web/vite.config.js`, `README.md`, this report

**Milestone G:**
- Created:
  - presets `presets/{iphone_17,iphone_17_pro,iphone_17_pro_max,iphone_air}.json`
  - components `web/src/components/{DevicePicker,DeviceEditor,DeviceDiagram}.jsx`
  - `web/src/fitLimits.js`
- Modified:
  - engine: `params.py` (`camera.ring`, `brand`, `year`, rules), `patterns.py` (open cut-out, MagSafe constants), `cad_engine.py` (open cut-out, part memo, `print_offset`, `laser_svg_text`, `CUT_TOL`, exact MagSafe cutter), `dfm.py` (`tessellate`), `bambu_3mf.py` (`set_objects_from_meshes`, optional ring), `print_in_place.py`, `server.py` (preview pipeline, ring-less export message, camera finding), `cli_test.py`
  - presets: all 10 existing (brand and year; MagSafe offsets on Galaxy S24, S24 Ultra and OnePlus 13; Galaxy S24 speaker), `schema/phone_preset.schema.json`
  - frontend: `web/src/{App.jsx,api.js}`, `web/src/components/{Fields,Viewport3D,PlatePreview,PatternPreviewCard}.jsx`
  - tests: `test_api.py`, `test_validation.py`, `test_geometry.py`, `test_desktop.py`, `test_regressions.py`, `test_printer_export.py`
  - docs: `README.md`, this report

**Milestone H:**
- Created: `test_ergonomics.py`, `web/src/components/ErgonomicsControls.jsx`
- Modified:
  - engine: `params.py` (new `Style` and `Port.chamfer` fields, flare and groove layout, rules), `patterns.py` (lanyard pocket, keep-out, preview), `cad_engine.py` (port flare loft, grip grooves, flex slits, lanyard pocket, `part_key`), `server.py` (lanyard finding), `cli_test.py` (new flags)
  - `schema/phone_preset.schema.json` (full `style` block, `ports[].chamfer`)
  - frontend: `web/src/App.jsx`, `web/src/fitLimits.js`, `web/src/components/{PatternControls,PlatePreview,DeviceEditor}.jsx`
  - docs: `README.md`, this report

## C. Testing results

The final runs were on 2026-11-18, Windows 11, Python 3.12.

**Python test suites:**

| Command | Result |
|---|---|
| `python -m pytest -m "not slow"` | **44 passed**, 36 deselected (14.4 s) |
| `python -m pytest` | **80 passed**, 0 failed, 0 skipped (2 m 53 s) |
| `python -m pytest test_printer_export.py -k overflow` | **2 passed**. Re-run after the overflow fallback fix added an "undersized bed" case, so the suite now has 81 tests. |

**CLI gates and other checks:**

| Command | Result |
|---|---|
| `python cli_test.py --preset iphone_16_pro --pattern voronoi --mode through --magsafe` | **56/56** checks; the export took 7.8 s (baseline 14.0 s, of which export_set was a part) |
| `python cli_test.py --preset iphone_15_pro --pattern hex --mode inlay --printer bambu_h3c` | **70/70**, including the explicit toolchanger material assignment and lib3mf strict reads; 18.2 s including the print-in-place gap report |
| `python cli_test.py --preset iphone_15_pro --pattern text --mode through` | exit 0 (stencil bridges keep the text connected) |
| `python cli_test.py --coupon` (camera, default) | **27/27** |
| `python cli_test.py --preset iphone_16_pro --coupon --coupon-type buttons` | **52/52** |
| `python cli_test.py --preset galaxy_s24 --coupon --coupon-type ports` | **17/17** |
| `python verify_3mf.py --make-fixtures …` | **7/7** files from the 5 fixtures pass the independent validator **and** lib3mf 2.5.0 strict mode |
| `cd web && npm run build` | builds (pre-existing 1.1 MB chunk warning) |
| Manual UI check (built app on uvicorn, in-app browser) | see below |

The manual UI check confirmed:
- the wizard and Pro mode both render
- the device verification badges and printer selector show
- switching to the H3C updates the plate to 330 × 320 mm and lists the print-in-place warnings
- a through-cut "CASECRAFT" with stencil bridges off shows "Invalid design — export blocked", with the 3-region message, and the export buttons are disabled
- the camera outer-opening fields work

**Preview performance** (hex through, iPhone 15 Pro): frame 0.40 s, backplate 0.71–1.06 s, ring 0.14 s, buttons 0.07 s. That is unchanged from the baseline within noise. Unibody generation takes 0.3–2.0 s (the old fuse approach took 0.6–2.4 s).

**Failing tests:** none. **Skipped:** none.

**GitHub Actions** (2026-11-18, `ubuntu-latest`, Python 3.12, Node 22):
- The first run, on `fc31f1c`, failed in the H3C CLI gate. `cli_test.py` loads `Backplate_Multicolor.3mf` with trimesh, whose 3MF reader needs `lxml`. That package was present locally only as a dependency of an unrelated package, and was not declared.
- `eec46cb` declares `lxml` in `requirements-dev.txt`. Its push and pull-request runs pass all three jobs: fast tests, the slow geometry/export job (including the coupon gates and the 3MF reference fixtures) and the frontend build.

**Not executed:**
- any slicer import
- any physical print

**Pre-existing failures vs regressions:**
- The existing suites had no pre-existing failures.
- These changes introduced no regressions. The original `test_regressions.py` (11 tests) still passes unchanged inside the full run.
- The intended behavior changes are documented and covered by the updated tests:
  - The default printer's bundle no longer contains `Toolchanger_InPlace.3mf`.
  - Through-cut islands are rejected instead of only logged.
  - The waves slot width changed.

## D. Engineering limitations

- **No slicer verification.** No file has been imported into Bambu Studio or OrcaSlicer by this project. The `model_settings.config` slot assignment follows the observed Bambu format, but Bambu Studio may not apply third-party assignments (Toposaic documents an import dialog for foreign color files).
- **No physical verification.** All presets are approximate (origin of the dimensions not recorded). Clearance "recommended ranges" and the print-in-place gap thresholds are heuristics, not measured values.
- **Print-in-place is unproven.** As generated, the backplate and buttons print in contact with the TPU. Widening `backplate_snap_clearance` to 0.4 mm gives a printable gap in the probe, but that makes a looser snap, and the buttons stay in contact at rest.
- **Unibody camera:** the surround is flush, with no raised lens guard, and the case is flexible single material by design.
- **H3C dimensions** come from secondary sources (the manufacturer page returned 403).
- **Camera envelope** supports one rounded-rectangle base and one outer opening, with a ruled loft only. It does not model the bump height or multiple islands.
- **Open camera cut-out has no lens guard.** On the iPhone 17 Pro, Pro Max and Air the plateau stands 0.75–1.23 mm proud of the case back, and the lens rings a further 1.88 mm or more. The modular case leaves the plateau open: the frame prints back-down, so it cannot grow a raised rim around the plateau without supports.
- **Camera plateaus are modelled as a full-width band** down to their lowest point (48.9 mm on the 17 Pro/Pro Max, 34.4 mm on the Air). Where the real plateau edge curves up, the case over-cuts slightly, which is safe for fit.
- **Text patterns on Linux CI** depend on system fonts. Arial is substituted, via `fonts-liberation`, which can shift text metrics slightly from Windows.
- **CI covers one platform.** GitHub Actions runs on Ubuntu with Python 3.12 only. Windows is checked only by the local runs above. The workflow's actions (`checkout@v4`, `setup-python@v5`, `setup-node@v4`, `upload-artifact@v4`) target the deprecated Node.js 20 runtime and should be upgraded.
- **Server CAD is serialized** by a single lock. Abandoned preview requests are now skipped, but a single slow request still blocks others.
- **The frontend bundle:** Milestone F lazy-loads the 3D viewer. The entry chunk is ~245 kB, but the Three.js chunk is still ~900 kB, and the Vite warning limit was raised to 1000 kB to cover it.
- **Pattern previews are 2D only.** The instant preview shows the cut-outs and the connectivity verdict, not deboss depth or the inlay sub-part; those appear only in the 3D rebuild.

## E. Manual verification checklist (Bambu Lab H3C)

See [MANUFACTURING_VERIFICATION.md](MANUFACTURING_VERIFICATION.md#manual-checklist-for-a-real-bambu-lab-h3c). In short:
1. **Fit coupons:** camera and snap, then buttons, then ports. Tune clearances until they fit.
2. **Modular print:** check filaments in the slicer, print, assemble, test lip, ports, buttons, MagSafe and the camera field of view.
3. **Print-in-place experiment:** read the gap report, check toolheads in the slicer, print, try to separate, record the material pair and the outcome.
4. **Update the preset's `verification`** only with evidence.

## F. Future work (prioritized)

1. **Physical and slicer validation run** on an H3C and one single-nozzle printer, using the five fixtures and three coupons. This would turn the heuristic clearance ranges into measured ones and settle whether Bambu Studio honors the slot assignment.
2. **Caliper-verified dimensions for the two most-used presets**, with recorded sources, so at least some presets move beyond `approximate`.
3. **A print-in-place clearance profile.** If the experiment shows bonding, add separate co-print clearances (snap gap ≥ 2 layers, buttons modelled off their pocket ceiling) instead of changing the snap-fit defaults.
4. **Camera bump height in the preset**, so the ring and unibody can warn when the lens protrudes past the bezel.
5. **Trim the Three.js chunk.** Milestone F lazy-loads the viewer (entry ~245 kB), but the 3D chunk is still ~900 kB; importing only the used drei helpers would shrink it.
6. **Physical prints of the new patterns,** especially `fade` and `corner_radius`, to confirm that the 2 mm² smallest faded cell and the rounded corners hold up on a real FDM print.
7. **Fit-test the iPhone 17 family** (camera and buttons coupons), then decide whether a clip-on plateau guard is worth adding for lens protection.
8. **Print the Milestone H features:** a ports coupon at 0, 0.6 and 1.2 mm chamfer with a real cable, a unibody with and without flex slits to compare the button press, and a backplate with the lanyard pocket against a real tether card.
9. **Newer Android presets** (Galaxy S25 series, Pixel 10 series) from the makers' dimensional data where it is published.

## External references consulted

These were used as engineering references only; no code was copied.

| Project | License | Used for |
|---|---|---|
| SiloCityLabs/Cuttlephone | CC BY-SA 4.0 | hard/soft material split (page has little fit detail) |
| zmacario/iphone13-rugged-case | MIT (code), CC BY-SA 4.0 (design) | camera island wider at base than plateau, asymmetric flared opening, targeted fit coupons, measuring walls directly |
| SlyWombat/CaseMaker | Apache-2.0 | provenance shown rather than a "verified" badge, data-file device library, UI/geometry separation |
| agocs/casefinity | MIT | headless smoke builds and ground-truth regression testing |
| theatrus/toposaic | Apache-2.0 | Bambu Studio vs OrcaSlicer handling of third-party 3MF color/filament data |
| 3MFConsortium/lib3mf | BSD-2-Clause | strict-mode independent validation (used as an optional dev dependency) |

CaseCraft itself has no license file; choosing one is an outstanding decision for the owner.
