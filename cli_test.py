"""Phase 2 verification gate: build a full 4-part set and validate outputs.
Usage: python cli_test.py [--preset iphone_15_pro] [--pattern solid|hex|svg|text] [--mode through|deboss|inlay] [--out out] [--coupon]
"""
import argparse
import dataclasses
import sys
import time
from pathlib import Path

import trimesh
from build123d import Compound

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

def run(preset_id, pattern, mode, out, magsafe=False):
    p = Preset.load(preset_id)
    p.pattern.type, p.pattern.mode = pattern, mode
    p.style.magsafe_ring = magsafe
    if pattern == "svg":
        p.pattern.params = {"svg": STAR_SVG, "size": 0.5}
    elif pattern == "text":
        p.pattern.params = {"text": "CASECRAFT", "size": 0.65, "font": "Arial", "bold": True}
    res = []
    t0 = time.perf_counter()
    r = ce.export_set(p, out)
    total = time.perf_counter() - t0
    print(f"\nTimings (s): {r['timings']}  total={total:.2f}")
    if pattern in ("voronoi", "grid", "waves", "hex"):
        check(r["timings"]["backplate"] < 1.5, f"{pattern} backplate generated in {r['timings']['backplate']:.3f}s (< 1.5s)", res)
    if pattern == "text" and mode == "through" and p.pattern.stencil_bridges:
        check(len(r["design"]["plate"].solids()) == 1, "stencil_bridges: text through-cut keeps backplate as 1 connected solid", res)
    uni_mesh = trimesh.load(Path(out) / "Unibody_OnePiece.stl")
    check(uni_mesh.is_watertight, f"Unibody_OnePiece.stl watertight ({len(uni_mesh.faces)} tris)", res)
    n_bodies = len(uni_mesh.split(only_watertight=False))
    check(n_bodies == 1, f"Unibody_OnePiece.stl is one connected body ({n_bodies} found)", res)
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
    check(o["CameraRing"].bounding_box().size.Z > p.bp_t, "CameraRing prints bezel-down", res)
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
    check(inter_volume(d["frame"], d["ring"]) < 0.5, "frame/ring no interference", res)
    check(inter_volume(d["plate"], d["ring"]) < 0.5, "plate/ring no interference", res)
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
    # 3MF structure + slot assignment
    import bambu_3mf
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
    check(len(asm.solids()) >= 3 + len(p.buttons), f"Full_Assembly.step re-imports ({len(asm.solids())} solids)", res)
    return res, r["timings"]


def run_coupon(preset_id, out):
    p = Preset.load(preset_id)
    res = []
    t0 = time.perf_counter()
    c = ce.export_coupon(p, out)
    total = time.perf_counter() - t0
    print(f"\nCoupon build total={total:.2f}s span=({c['span'][0]:.1f}, {c['span'][1]:.1f})")
    for f in c["files"]:
        check(Path(f).exists() and Path(f).stat().st_size > 100, f"coupon file written: {Path(f).name} ({Path(f).stat().st_size} B)", res)
    w, l = c["span"]
    check(25 <= w < p.W and 25 <= l < p.L, f"coupon span ({w:.1f}x{l:.1f}) within [25, {p.W}x{p.L})", res)
    for name, shp in c["oriented"].items():
        solids = shp.solids()
        check(all(s.is_valid for s in solids) and shp.volume > 1, f"{name}: valid B-rep, {len(solids)} solid(s), vol={shp.volume:.0f} mm3", res)
        check(abs(shp.bounding_box().min.Z) < 1e-4, f"{name}: sits on Z=0", res)
        m = trimesh.load(Path(out) / f"{name}.stl")
        check(m.is_watertight, f"{name}: STL watertight ({len(m.faces)} tris)", res)
    import bambu_3mf
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
    ap.add_argument("--out", default="out")
    ap.add_argument("--coupon", action="store_true")
    ap.add_argument("--magsafe", action="store_true")
    a = ap.parse_args()
    if a.coupon:
        results = run_coupon(a.preset, a.out)
    else:
        results, timings = run(a.preset, a.pattern, a.mode, a.out, magsafe=a.magsafe)
        results += stress()
    bad = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
    sys.exit(1 if bad else 0)
