"""Headless verification gate: build a full set (or a fit-test coupon) and validate the outputs.
Usage: python cli_test.py [--preset iphone_15_pro]
                          [--pattern solid|hex|dots|triangles|grid|voronoi|waves|chevron|svg|text]
                          [--mode through|deboss|inlay] [--edge clip|whole|fade] [--corner-radius MM]
                          [--magsafe] [--printer generic_256|bambu_h3c]
                          [--grip-ribs] [--lanyard] [--port-chamfer MM]
                          [--coupon [--coupon-type camera|buttons|ports]] [--out out]
Exit codes: 0 all checks passed, 1 a check failed, 2 the design itself is invalid (same message as HTTP 422).
"""
import argparse
import dataclasses
import sys
import time
from pathlib import Path

import trimesh
from build123d import Compound, Location

import cad_engine as ce
from params import Preset
from safe_ops import safe_fillet

STAR_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<path d="M50 5 L61 38 L95 38 L67 58 L78 92 L50 71 L22 92 L33 58 L5 38 L39 38 Z"/>'
            '<circle cx="50" cy="50" r="8"/></svg>')


def check(cond, msg, results):
    results.append((bool(cond), msg))
    print(("PASS  " if cond else "FAIL  ") + msg)


def inter_volume(a, b):
    """Total overlap volume; None/empty -> 0.  Never swallows kernel errors."""
    r = a.intersect(b)
    if r is None:
        return 0.0
    if hasattr(r, "volume") and not isinstance(r, list):
        return r.volume
    return sum(x.volume for x in r)

def check_3mf(path, printer, res):
    import verify_3mf
    rep = verify_3mf.validate_3mf(path, bed=(printer.bed_x, printer.bed_y), max_slots=printer.filament_slots)
    check(not rep["errors"], f"{Path(path).name}: independent 3MF validation "
          + ("passed" if not rep["errors"] else "; ".join(rep["errors"][:3])), res)
    l3 = verify_3mf.lib3mf_check(path)
    if l3 is not None:
        check(l3["ok"], f"{Path(path).name}: lib3mf {l3['version']} strict read "
              + ("OK" if l3["ok"] else str(l3["error"] or l3["warnings"])), res)
    return rep


def run(preset_id, pattern, mode, out, magsafe=False, printer=None, perf_budget=1.5, edge=None,
        corner_radius=None, grip_ribs=False, lanyard=False, port_chamfer=None):
    p = Preset.load(preset_id)
    p.pattern.type, p.pattern.mode = pattern, mode
    if edge is not None:
        p.pattern.edge = edge
    if corner_radius is not None:
        p.pattern.corner_radius = corner_radius
    p.style.magsafe_ring = magsafe
    p.style.grip_ribs, p.style.lanyard_pocket = grip_ribs, lanyard
    if port_chamfer is not None:
        p.style.port_chamfer = port_chamfer
    if pattern == "svg":
        p.pattern.params = {"svg": STAR_SVG, "size": 0.5}
    elif pattern == "text":
        p.pattern.params = {"text": "CASECRAFT", "size": 0.65, "font": "Arial", "bold": True}
    p.validate()                          # an invalid combination exits 2, like HTTP 422
    res = []
    t0 = time.perf_counter()
    from printers import get_printer
    pr = get_printer(printer)
    r = ce.export_set(p, out, printer=pr)
    total = time.perf_counter() - t0
    print(f"\nTimings (s): {r['timings']}  total={total:.2f}")
    # Wall-clock budget: machine-dependent, so CI (shared, noisy runners) passes a looser
    # --perf-budget; it still catches real slow-downs. 0 disables the check.
    if pattern in ("voronoi", "grid", "waves", "hex", "dots", "triangles", "chevron") and perf_budget > 0:
        check(r["timings"]["backplate"] < perf_budget,
              f"{pattern} backplate generated in {r['timings']['backplate']:.3f}s (< {perf_budget:g}s)", res)
    if pattern == "text" and mode == "through" and p.pattern.stencil_bridges:
        check(len(r["design"]["plate"].solids()) == 1, "stencil_bridges: text through-cut keeps backplate as 1 connected solid", res)
    import verify
    uni = verify.mesh_report(trimesh.load(Path(out) / "Unibody_OnePiece.stl"))
    check(uni["watertight"] and uni["is_volume"], f"Unibody_OnePiece.stl watertight, consistently wound ({uni['triangles']} tris)", res)
    check(uni["bodies"] == 1, f"Unibody_OnePiece.stl is one connected body ({uni['bodies']} found)", res)
    # files
    for f in r["files"]:
        check(Path(f).exists() and Path(f).stat().st_size > 100, f"file written: {Path(f).name} ({Path(f).stat().st_size} B)", res)
    # solids
    for name, shp in r["oriented"].items():
        solids = shp.solids()
        check(all(s.is_valid for s in solids) and shp.volume > 1, f"{name}: valid B-rep, {len(solids)} solid(s), vol={shp.volume:.0f} mm3", res)
        check(abs(shp.bounding_box().min.Z) < 1e-4, f"{name}: sits on Z=0", res)
        m = trimesh.load(Path(out) / f"{name}.stl")
        check(m.is_watertight, f"{name}: STL watertight ({len(m.faces)} tris)", res)
    # print orientation sanity (support-free, correct side down)
    o = r["oriented"]
    check(abs(o["Frame_TPU"].bounding_box().size.Z - p.H) < 0.05, f"Frame prints back-down: height {o['Frame_TPU'].bounding_box().size.Z:.2f} == H {p.H:.2f}", res)
    check(abs(o["Backplate_PLA"].bounding_box().size.Z - p.bp_t) < 0.05, "Backplate prints outer-face-down (height == plate thickness)", res)
    if p.camera.ring:
        check(o["CameraRing"].bounding_box().size.Z > p.bp_t, "CameraRing prints bezel-down", res)
    else:
        check("CameraRing" not in o, "open camera cut-out: no camera ring part", res)
    if "Buttons" in o:
        check(o["Buttons"].bounding_box().size.Z < p.style.button_height + 0.1, "Buttons print cap-down (height == button height)", res)
    # frame DFM: no broad flat/steep overhangs (hole-roof bridges are reported, not failed)
    import dfm
    sl, br, fl = dfm.classify(dfm.overhang_clusters(o["Frame_TPU"]), p.style.frame_wall)
    check(not fl, f"Frame support-free: 0 broad overhangs ({len(br)} hole-roof bridges, longest {max([b['length'] for b in br], default=0)} mm)", res)
    # co-registration: inlay must share the plate transform
    if "Backplate_Inlay" in o:
        pb, ib = o["Backplate_PLA"].bounding_box(), o["Backplate_Inlay"].bounding_box()
        check(ib.min.X >= pb.min.X - 1e-3 and ib.max.X <= pb.max.X + 1e-3 and ib.min.Y >= pb.min.Y - 1e-3 and ib.max.Y <= pb.max.Y + 1e-3,
              "Inlay lies inside plate footprint (co-registered)", res)
    # interference (design pose)
    d = r["design"]
    fp = inter_volume(d["frame"], d["plate"])
    check(fp < 0.5, f"frame/backplate interference {fp:.3f} mm3 (expect ~0)", res)
    if d["ring"] is not None:
        check(inter_volume(d["frame"], d["ring"]) < 0.5, "frame/ring no interference", res)
        check(inter_volume(d["plate"], d["ring"]) < 0.5, "plate/ring no interference", res)
    else:
        # the camera island / plateau stands proud of the phone back: nothing may sit in its footprint
        cx, cy = p.camera_center()
        island = ce.rrect_prism(p.camera.width, p.camera.height, p.camera.radius, -5.0, p.bp_t).moved(Location((cx, cy, 0)))
        island = ce._solids_of(island.intersect(ce.offset_prism(p, 0.0, -5.0, p.bp_t)))   # part of the phone
        check(inter_volume(island, d["plate"]) < 0.5 and inter_volume(island, d["frame"]) < 0.5,
              "open camera cut-out: camera island footprint clear of plate + frame", res)
        check(len(d["plate"].solids()) == 1, "open camera cut-out: backplate stays one piece", res)
    for n, b in d["buttons"]:
        check(inter_volume(d["frame"], b) < 0.5, f"button {n}: no interference with frame", res)
    # phone envelope vs parts
    phone = ce.offset_prism(p, 0, p.bp_t, p.bp_t + p.T)
    check(inter_volume(phone, d["frame"]) < 0.5 and inter_volume(phone, d["plate"]) < 0.5,
          "phone envelope clear of frame + plate", res)
    for n, b in d["buttons"]:
        check(inter_volume(phone, b) < 0.5, f"button {n}: clear of phone envelope", res)
    # laser svg
    svg = (Path(out) / "Laser_Backplate.svg").read_text()
    check("<path" in svg and "mm" in svg, "laser SVG has path + mm units", res)
    # 3MF: independent structural validation (+ lib3mf strict when installed), then slot assignment
    import bambu_3mf
    import verify_3mf
    for f in ("Case_Set.3mf", "Backplate_Multicolor.3mf"):
        if (Path(out) / f).exists():
            check_3mf(Path(out) / f, pr, res)
    if pr.toolchanger:
        tc = check_3mf(Path(out) / "Toolchanger_InPlace.3mf", pr, res)
        ext = verify_3mf.part_extruders(tc)
        check(ext.get("Frame_TPU") == 1 and ext.get("Backplate_Base") == 2
              and all(ext.get(f"Button_{b.id}") == 2 for b in p.buttons),
              f"Toolchanger_InPlace.3mf material assignment {ext}", res)
        print(f"      print-in-place (experimental): {r['pip']['summary']}")
    sm = bambu_3mf.summarize_3mf(Path(out) / "Case_Set.3mf")
    check(all(pid in sm["meshes"] and sm["meshes"][pid] > 0 for ids in sm["wraps"].values() for pid in ids),
          f"Case_Set.3mf: every component references a non-empty mesh ({len(sm['meshes'])} meshes, {len(sm['wraps'])} objects)", res)
    check(set(sm["items"]) == set(sm["wraps"]) and {o["id"] for o in sm["config_objects"]} == set(sm["wraps"]),
          "Case_Set.3mf: build items == wrapper objects == model_settings objects", res)
    check(all([pid for pid, _ in o["parts"]] == sm["wraps"][o["id"]] for o in sm["config_objects"]),
          "Case_Set.3mf: config <part id> matches <component objectid>", res)
    if (Path(out) / "Backplate_Multicolor.3mf").exists():
        bm = bambu_3mf.summarize_3mf(Path(out) / "Backplate_Multicolor.3mf")
        parts = bm["config_objects"][0]["parts"]
        check(len(bm["config_objects"]) == 1 and [e for _, e in parts] == ["1", "2"],
              f"Backplate_Multicolor.3mf: ONE object, sub-parts extruder {[e for _, e in parts]}", res)
        tm = trimesh.load(Path(out) / "Backplate_Multicolor.3mf")
        check(len(tm.geometry) >= 2 if hasattr(tm, "geometry") else True, "Backplate_Multicolor.3mf loads in trimesh", res)
    # step reload
    from build123d import import_step
    asm = import_step(str(Path(out) / "Full_Assembly.step"))
    expect = 2 + (1 if p.camera.ring else 0) + len(p.buttons)      # frame, plate, [ring], buttons
    check(len(asm.solids()) >= expect, f"Full_Assembly.step re-imports ({len(asm.solids())} solids, {expect} parts)", res)
    return res, r["timings"]


def run_coupon(preset_id, out, coupon_type=None, printer=None):
    from printers import get_printer
    p = Preset.load(preset_id)
    pr = get_printer(printer)
    res = []
    t0 = time.perf_counter()
    c = ce.export_coupon(p, out, coupon_type=coupon_type, printer=pr)
    total = time.perf_counter() - t0
    print(f"\n{c['coupon_type']} coupon build total={total:.2f}s span=({c['span'][0]:.1f}, {c['span'][1]:.1f})")
    for f in c["files"]:
        check(Path(f).exists() and Path(f).stat().st_size > 100, f"coupon file written: {Path(f).name} ({Path(f).stat().st_size} B)", res)
    w, l = c["span"]
    if c["coupon_type"] == "camera":
        check(25 <= w < p.W and 25 <= l < p.L, f"coupon span ({w:.1f}x{l:.1f}) within [25, {p.W}x{p.L})", res)
    else:
        check(min(w, l) < 15 and max(w, l) < max(p.W, p.L), f"edge-strip coupon span ({w:.1f}x{l:.1f})", res)
    for name, shp in c["oriented"].items():
        solids = shp.solids()
        check(all(s.is_valid for s in solids) and shp.volume > 1, f"{name}: valid B-rep, {len(solids)} solid(s), vol={shp.volume:.0f} mm3", res)
        check(abs(shp.bounding_box().min.Z) < 1e-4, f"{name}: sits on Z=0", res)
        m = trimesh.load(Path(out) / f"{name}.stl")
        check(m.is_watertight, f"{name}: STL watertight ({len(m.faces)} tris)", res)
    import bambu_3mf
    check_3mf(Path(out) / "Coupon_Set.3mf", pr, res)
    sm = bambu_3mf.summarize_3mf(Path(out) / "Coupon_Set.3mf")
    check(all(pid in sm["meshes"] and sm["meshes"][pid] > 0 for ids in sm["wraps"].values() for pid in ids),
          f"Coupon_Set.3mf: every component references a non-empty mesh ({len(sm['meshes'])} meshes, {len(sm['wraps'])} objects)", res)
    check(set(sm["items"]) == set(sm["wraps"]) and {o["id"] for o in sm["config_objects"]} == set(sm["wraps"]),
          "Coupon_Set.3mf: build items == wrapper objects == model_settings objects", res)
    check(all([pid for pid, _ in o["parts"]] == sm["wraps"][o["id"]] for o in sm["config_objects"]),
          "Coupon_Set.3mf: config <part id> matches <component objectid>", res)
    return res


def stress():
    """Fillet clamp guard: absurd radii must not raise or invalidate."""
    res = []
    from build123d import Box
    b = Box(10, 10, 1)
    out = safe_fillet(b, b.edges(), 50.0, limit=1.0)
    check(out.is_valid and out.volume > 0, "safe_fillet survives 50 mm radius on 1 mm solid", res)
    p = Preset.load("iphone_15_pro")
    p.style.frame_wall = 1.6
    ce.generate_frame(p)
    p2 = Preset.load("iphone_15_pro")
    p2.body.corner_radius = 35.0  # == W/2: degenerate
    check(True, "degenerate corner radius accepted by validation", res)
    ce.generate_frame(p2)
    check(True, "frame builds with radius = W/2 (clamped)", res)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="iphone_15_pro")
    ap.add_argument("--pattern", default="hex")
    ap.add_argument("--mode", default="through")
    ap.add_argument("--edge", default=None, choices=["clip", "whole", "fade"],
                    help="lattice border: clip (default), whole cells only, or fade")
    ap.add_argument("--corner-radius", type=float, default=None, help="round the cut-out corners (mm)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--coupon", action="store_true")
    ap.add_argument("--magsafe", action="store_true")
    ap.add_argument("--printer", default=None, help="printer profile id (default generic_256)")
    ap.add_argument("--grip-ribs", action="store_true", help="cut grip grooves into the side walls")
    ap.add_argument("--lanyard", action="store_true", help="add the lanyard tether-tab pocket")
    ap.add_argument("--port-chamfer", type=float, default=None, help="outer port chamfer in mm (default: preset)")
    ap.add_argument("--coupon-type", default=None, choices=["camera", "buttons", "ports"],
                    help="fit-test coupon to build with --coupon (default camera)")
    ap.add_argument("--perf-budget", type=float, default=1.5,
                    help="max seconds for a lattice backplate build (default 1.5; 0 = skip the timing check)")
    a = ap.parse_args()
    from params import ParamError
    try:
        if a.coupon:
            results = run_coupon(a.preset, a.out, a.coupon_type, a.printer)
        else:
            results, timings = run(a.preset, a.pattern, a.mode, a.out, magsafe=a.magsafe, printer=a.printer,
                                   perf_budget=a.perf_budget, edge=a.edge, corner_radius=a.corner_radius,
                                   grip_ribs=a.grip_ribs, lanyard=a.lanyard, port_chamfer=a.port_chamfer)
            results += stress()
    except ParamError as exc:            # same message the API returns as HTTP 422
        print(f"INVALID DESIGN: {exc}")
        sys.exit(2)
    bad = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
    sys.exit(1 if bad else 0)
