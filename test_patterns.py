"""Fast tests for the 2D pattern library (patterns.py): saved designs build exactly as before,
the new border modes / corner rounding / pattern types stay connected and printable, the UI
spec only offers valid values, and the live-preview endpoints. Run: pytest test_patterns.py"""
import copy
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

import patterns as pt
from params import EDGE_MODES, PATTERN_TYPES, Preset, stripe_cos

PRESETS = Path(__file__).parent / "presets"
STAR = pt.STAR_SVG
LATTICES = ("hex", "dots", "triangles", "grid", "voronoi")


def _raw(pid="iphone_15_pro"):
    return json.loads((PRESETS / f"{pid}.json").read_text(encoding="utf-8"))


def _preset(pid="iphone_15_pro", ptype="hex", mode="through", params=None, magsafe=False, **pattern):
    p = Preset.load(pid)
    p.pattern.type, p.pattern.mode = ptype, mode
    p.pattern.params = copy.deepcopy(params if params is not None else pt.PATTERN_SPECS[ptype]["defaults"])
    for k, v in pattern.items():
        setattr(p.pattern, k, v)
    p.style.magsafe_ring = magsafe
    p.validate()
    return p


# ------------------------------------------------------------------ saved designs are unchanged
# Recorded from the generator BEFORE the pattern library moved to patterns.py (count, area mm2,
# vertex count of the cut-outs). Default border (clip) and no rounding must reproduce them.
LEGACY = [
    ("iphone_15_pro", "hex", "through", {"pitch": 9.0}, False, 115, 4956.741, 860),
    ("iphone_15_pro", "hex", "deboss", {"pitch": 6.5}, True, 189, 3431.386, 1386),
    ("pixel_9_pro_xl", "hex", "inlay", {"pitch": 12.0}, False, 87, 6874.075, 729),
    ("iphone_16_pro", "voronoi", "through", {"pitch": 11.0, "seed": 42}, False, 82, 5647.318, 643),
    ("galaxy_s24_ultra", "voronoi", "deboss", {"pitch": 8.0, "seed": 7}, False, 182, 6372.197, 1355),
    ("iphone_16_pro", "grid", "through", {"pitch": 8.5, "angle": 45.0}, False, 108, 4956.856, 614),
    ("oneplus_13", "grid", "through", {"pitch": 10.0, "angle": 30.0}, False, 92, 5725.689, 644),
    ("iphone_15_pro", "svg", "through", {"svg": STAR, "size": 0.6}, False, 2, 421.327, 390),
    ("iphone_15_pro", "svg", "deboss", {"svg": STAR, "size": 0.8, "offset": [3.0, -5.0]}, False, 1, 801.767, 410),
]


@pytest.mark.parametrize("pid,ptype,mode,params,magsafe,count,area,verts", LEGACY)
def test_saved_designs_build_identically(pid, ptype, mode, params, magsafe, count, area, verts):
    p = _preset(pid, ptype, mode, params, magsafe)
    assert (p.pattern.edge, p.pattern.corner_radius) == ("clip", 0.0)      # what old files load as
    polys = pt.pattern_polys(p)
    assert len(polys) == count
    assert sum(g.area for g in polys) == pytest.approx(area, abs=0.05)
    nv = sum(len(g.exterior.coords) + sum(len(i.coords) for i in g.interiors) for g in polys)
    assert abs(nv - verts) <= 2, nv                   # tolerance: cross-platform float noise only


# ------------------------------------------------------------------ new options stay printable
@pytest.mark.parametrize("pid", ["iphone_16_pro", "galaxy_s24_ultra", "pixel_9_pro_xl"])
@pytest.mark.parametrize("ptype", ["hex", "dots", "triangles", "grid", "voronoi", "waves", "chevron"])
def test_new_options_keep_through_cuts_connected(pid, ptype):
    for edge in pt.PATTERN_SPECS[ptype]["edges"] or ["clip"]:
        for r in ((0.0, 1.0) if pt.PATTERN_SPECS[ptype]["rounding"] else (0.0,)):
            p = _preset(pid, ptype, edge=edge, corner_radius=r)
            conn = pt.through_cut_connectivity(p)
            assert conn["islands"] == [] and conn["thin_necks"] == 0, (edge, r, conn)
            assert len(pt.pattern_polys(p)) > 5, (edge, r)


@pytest.mark.parametrize("ptype", LATTICES)
def test_whole_border_keeps_only_complete_cells(ptype):
    p = _preset("iphone_15_pro", ptype, edge="whole")
    region = pt.pattern_region(p).buffer(1e-6)
    cells = pt.pattern_polys(p)
    assert cells and all(region.contains(g) for g in cells)
    if ptype != "voronoi":                            # identical tiles: no cut-off part cells
        areas = [g.area for g in cells]
        assert max(areas) - min(areas) < 0.01 * max(areas)


@pytest.mark.parametrize("ptype", ["hex", "dots"])
def test_fade_border_shrinks_cells_towards_the_edge(ptype):
    p = _preset("iphone_15_pro", ptype, edge="fade", fade_width=15.0)
    region = pt.pattern_region(p)
    cells = pt.pattern_polys(p)
    assert all(region.buffer(1e-6).contains(g) for g in cells)
    assert all(g.area >= pt.FADE_MIN_AREA - 1e-9 for g in cells)     # no unprintable specks
    near = [g.area for g in cells if region.boundary.distance(g.centroid) < 5]
    far = [g.area for g in cells if region.boundary.distance(g.centroid) > 15]
    assert near and far and max(near) < min(far)


@pytest.mark.parametrize("ptype", ["hex", "triangles", "grid", "voronoi", "waves", "chevron"])
def test_corner_rounding_only_trims_cutouts(ptype):
    edge = "whole" if ptype in LATTICES else "clip"
    sharp = unary_union(pt.pattern_polys(_preset("iphone_16_pro", ptype, edge=edge)))
    rounded = unary_union(pt.pattern_polys(_preset("iphone_16_pro", ptype, edge=edge, corner_radius=1.0)))
    # never grows a cut-out: exactly for lattices; stripes are drawn to 0.05-0.08 mm (both versions)
    tol = 1e-6 if ptype in LATTICES else 0.17
    assert rounded.difference(sharp.buffer(tol)).area < 1e-6
    assert rounded.area < sharp.area                                 # corners were trimmed
    # every convex corner now carries a ~1 mm arc: a slightly smaller opening changes nothing
    again = rounded.buffer(-0.95).buffer(0.95)
    assert rounded.symmetric_difference(again).area < 0.01 * rounded.area


def test_dots_are_exact_circles():
    p = _preset("iphone_15_pro", "dots", edge="whole")
    cells = pt.pattern_cells(p)
    r0 = (p.pattern.params["pitch"] - p.pattern.web) / 2
    assert cells and all(c.circle is not None and c.circle[2] == pytest.approx(r0) for c in cells)
    for c in cells[:25]:
        x, y, r = c.circle
        assert c.poly.area == pytest.approx(math.pi * r * r, rel=0.01)
        assert c.poly.centroid.distance(Point(x, y)) < 1e-6
    faded = pt.pattern_cells(_preset("iphone_15_pro", "dots", edge="fade"))
    assert all(c.poly.area == pytest.approx(math.pi * c.circle[2] ** 2, rel=0.01) for c in faded)


def test_waves_match_the_analytic_bands():
    """The old 24-sample polyline flattened every crest (visibly faceted); the bands must now
    follow the true sine within 0.1 mm."""
    p = _preset("iphone_15_pro", "waves")
    a, wl, pitch, web = 3.5, 28.0, 7.0, p.pattern.web
    region = pt.pattern_region(p)
    half = max(0.5, (pitch * stripe_cos(a, wl) - web) / 2)
    minx, miny, maxx, maxy = region.bounds
    xs = np.arange(minx - pitch, maxx + pitch, 0.05)
    bands, y0 = [], miny - a - pitch
    while y0 <= maxy + a + pitch:
        line = LineString([(x, y0 + a * math.sin(2 * math.pi * x / wl)) for x in xs])
        bands.append(line.buffer(half, cap_style="flat", quad_segs=16))
        y0 += pitch
    ideal = unary_union([g for g in pt._parts(unary_union(bands).intersection(region)) if g.area >= 2.0])
    got = unary_union(pt.pattern_polys(p))
    assert shapely.hausdorff_distance(got.boundary, ideal.boundary) < 0.1


def test_lattices_are_mirror_symmetric_with_new_borders():
    """whole/fade centre the lattice on the plate, so a symmetric plate gets a symmetric layout."""
    p = _preset("iphone_15_pro", "dots", edge="whole")
    p.camera.x = (p.W - p.camera.width) / 2                     # centre the camera island
    centres = {(round(c.circle[0], 3), round(c.circle[1], 3)) for c in pt.pattern_cells(p)}
    assert centres and all((round(-x, 3), y) in centres for x, y in centres)


# ------------------------------------------------------------------ validation of the new fields
@pytest.mark.parametrize("pattern,word", [
    ({"type": "hex", "edge": "blur"}, "pattern.edge"),
    ({"type": "hex", "corner_radius": -0.5}, "corner_radius"),
    ({"type": "hex", "corner_radius": 6.0}, "corner_radius"),
    ({"type": "hex", "fade_width": 1.0}, "fade_width"),
    ({"type": "triangles", "web": 3.0, "params": {"pitch": 6.0}}, "triangles"),
    ({"type": "dots", "web": 2.5, "params": {"pitch": 3.2}}, "dots"),
    ({"type": "chevron", "params": {"pitch": 4.5, "amplitude": 8, "wavelength": 10}}, "chevron too steep"),
    ({"type": "voronoi", "params": {"relax": 2.5}}, "relax"),
    ({"type": "voronoi", "params": {"relax": 6}}, "relax"),
    ({"type": "text", "params": {"text": "A", "font": 12}}, "font"),
    ({"type": "text", "params": {"text": "A", "offset": [1]}}, "offset"),
    ({"type": "text", "params": {"text": "A", "rotation": 400}}, "rotation"),
    ({"type": "svg", "params": {"svg": STAR, "size": 0}}, "size"),
    ({"type": "svg", "params": {"size": 0.5}}, "pattern.params.svg"),
])
def test_new_pattern_rules(pattern, word):
    d = _raw()
    d["pattern"] = {"mode": "through", **pattern}
    with pytest.raises(ValueError, match=re.escape(word)):
        Preset.from_dict(d)


def test_old_files_without_new_keys_still_load():
    d = _raw()
    d["pattern"] = {"type": "hex", "mode": "through", "depth": 0.8, "margin": 3.0, "web": 1.6,
                    "stencil_bridges": True, "params": {"pitch": 9.0}}
    p = Preset.from_dict(d)
    assert (p.pattern.edge, p.pattern.corner_radius, p.pattern.fade_width) == ("clip", 0.0, 15.0)


# ------------------------------------------------------------------ UI spec
def test_specs_cover_every_pattern_type():
    assert set(pt.PATTERN_SPECS) == set(PATTERN_TYPES)
    for t, spec in pt.PATTERN_SPECS.items():
        assert spec["label"] and spec["description"], t
        assert set(spec["edges"]) <= set(EDGE_MODES), t
        assert all(c["key"] in spec["defaults"] for c in spec["controls"]), t
    json.dumps(pt.public_specs())


@pytest.mark.parametrize("ptype", [t for t in PATTERN_TYPES if t != "solid"])
def test_every_slider_extreme_is_a_valid_design(ptype):
    """Each control the UI offers, at its min and max with everything else at its default."""
    spec = pt.PATTERN_SPECS[ptype]
    cases = [{}]
    for c in spec["controls"]:
        if c["kind"] in ("slider", "xy"):
            for v in (c["min"], c["max"]):
                cases.append({"params": {c["key"]: [v, v] if c["kind"] == "xy" else v}})
    for key, c in pt.SHARED_CONTROLS.items():
        for v in (c["min"], c["max"]):
            cases.append({key: v})
    for case in cases:
        d = _raw()
        params = {**copy.deepcopy(spec["defaults"]), **case.pop("params", {})}
        d["pattern"] = {"type": ptype, "mode": "through", "params": params, **case}
        Preset.from_dict(d)                                       # raises on any error


# ------------------------------------------------------------------ live preview
def _xs(path):
    return [float(m) for m in re.findall(r"[ML](-?[\d.]+) -?[\d.]+", path)]


def test_preview_paths_and_stats():
    out = pt.pattern_preview(_preset("iphone_15_pro", "hex"))
    assert out["view"] == "back" and len(out["viewBox"]) == 4
    assert out["frame"].startswith("M") and out["plate"].startswith("M") and out["camera"].startswith("M")
    assert out["cuts"].count("M") == out["stats"]["cuts"] == 115
    assert 20 < out["stats"]["open_area_pct"] < 80
    assert out["error"] is None and out["islands"] == "" and out["connectivity"]["islands"] == 0
    json.dumps(out)


def test_preview_is_drawn_as_seen_from_the_back():
    # an emblem moved to the phone's right (design +X) appears on the LEFT of the back view
    p = _preset("iphone_15_pro", "svg", params={"svg": STAR, "size": 0.3, "offset": [15.0, -20.0]})
    xs = _xs(pt.pattern_preview(p)["cuts"])
    assert xs and max(xs) < 0


def test_preview_shows_loose_pieces_instead_of_failing():
    p = _preset("iphone_15_pro", "text", params={"text": "OO", "size": 0.6}, stencil_bridges=False)
    out = pt.pattern_preview(p)
    assert out["connectivity"]["islands"] == 2 and out["islands"].count("M") == 2
    assert "disconnected" in out["error"]


def test_preview_reports_magsafe_clash_as_an_error():
    p = _preset("iphone_15_pro", "hex", mode="deboss", magsafe=True)
    p.style.magsafe_offset_y = 30.0                               # into the camera cutout
    out = pt.pattern_preview(p)
    assert "MagSafe ring overlaps" in out["error"] and out["cuts"] == "" and out["magsafe"]


def test_pattern_cells_are_cached_but_isolated():
    p = _preset("iphone_15_pro", "voronoi")
    first = pt.pattern_polys(p)
    expected = list(first)
    first.clear()                                                 # a caller mutating its list...
    assert pt.pattern_polys(p) == expected                        # ...does not touch the cache
    q = copy.deepcopy(p)
    q.pattern.params["seed"] = 7
    assert pt.pattern_polys(q) != expected


def test_pattern_endpoints():
    from fastapi.testclient import TestClient
    from server import app
    client = TestClient(app)
    specs = client.get("/api/patterns").json()
    assert [t["id"] for t in specs["types"]] == list(pt.PATTERN_SPECS)
    assert {e["id"] for e in specs["edges"]} == set(EDGE_MODES) and specs["fonts"]
    d = _raw()
    d["pattern"] = {"type": "dots", "mode": "through", "edge": "fade", "params": {"pitch": 7.0}}
    r = client.post("/api/pattern-preview", json=d)
    assert r.status_code == 200 and r.json()["stats"]["cuts"] > 50, r.text
    g = client.post("/api/pattern-gallery", json=d).json()
    assert set(g["types"]) == set(pt.PATTERN_SPECS)
    assert all(g["types"][t] is not None for t in g["types"]), g["types"]
    d["pattern"]["edge"] = "blur"
    assert client.post("/api/pattern-preview", json=d).status_code == 422
