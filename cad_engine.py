"""CaseCraft headless CAD engine (build123d / OpenCascade).

Public API:
    generate_frame(p), generate_backplate(p), generate_camera_ring(p), generate_buttons(p)
    apply_backplate_pattern(plate, p)  -> (plate, inlay_or_None)
    orient_for_print(shape), laser_svg(p, path), export_set(p, out_dir)
Design pose: see params.py docstring (z=0 = outer backplate face, phone at +Z).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path

from build123d import (Box, Circle, Compound, Face, Location, Plane, Pos, RectangleRounded, Rot,
                       Solid, Vector, Wire, export_step, export_stl)
from shapely.geometry import Polygon
from shapely.ops import unary_union

from params import ParamError, Preset
# 2D geometry lives in patterns.py; re-exported here for existing callers (server, tests, CLI)
from patterns import (Cell, _polys, camera_cutout_dims, camera_cutout_poly, check_through_cut,  # noqa: F401
                      magsafe_pocket_poly, magsafe_ring_poly, pattern_cells, pattern_polys,
                      plate_outline_poly, rrect_poly, svg_to_polys, text_to_polys,
                      through_cut_connectivity, through_cut_material)
from safe_ops import safe_chamfer, safe_corner_radius, safe_fillet

log = logging.getLogger("casecraft")
EPS = 0.01
SIDE_ANGLE = {"right": 0, "top": 90, "left": 180, "bottom": 270}


# ----------------------------------------------------------------------------- part memo
# The frame, camera ring and buttons do not depend on the backplate pattern, which is what a
# user changes most. They are memoised on exactly the parameters they read, so a pattern edit
# (and the export that follows a preview) only rebuilds the backplate. Shapes are never mutated
# in place (every transform returns a new shape), so sharing them is safe.
_PART_CACHE: OrderedDict = OrderedDict()
_PART_CACHE_MAX = 32
_part_lock = threading.Lock()
_NOT_FRAME = ("camera_", "magsafe_")


def part_key(p: Preset, part: str) -> str:
    """Canonical key of the parameters one part's geometry depends on (frame | ring | buttons |
    phone). Over-inclusive is only a cache miss; never leave out something the generator reads."""
    d = dataclasses.asdict(p)
    style = d["style"]
    if part == "frame":
        deps = [d["body"], d["clearances"], {k: v for k, v in style.items() if not k.startswith(_NOT_FRAME)},
                d["buttons"], d["ports"]]
    elif part == "ring":
        deps = [d["body"], d["camera"], style, d["clearances"]]
    elif part == "buttons":
        deps = [d["body"], d["buttons"], style, d["clearances"]]
    elif part == "phone":
        deps = [d["body"], style["backplate_thickness"]]
    else:
        raise ValueError(f"unknown part {part!r}")
    return part + ":" + json.dumps(deps, sort_keys=True, separators=(",", ":"))


def _memo(key: str, build):
    with _part_lock:
        if key in _PART_CACHE:
            _PART_CACHE.move_to_end(key)
            return _PART_CACHE[key]
    value = build()
    with _part_lock:
        _PART_CACHE[key] = value
        while len(_PART_CACHE) > _PART_CACHE_MAX:
            _PART_CACHE.popitem(last=False)
    return value


def clear_part_cache() -> None:
    with _part_lock:
        _PART_CACHE.clear()


# ----------------------------------------------------------------------------- helpers
def rrect_prism(w: float, l: float, r: float, z0: float, z1: float) -> Solid:
    """Rounded-rectangle prism between z0 and z1 (radius auto-clamped)."""
    r = safe_corner_radius(r, w, l)
    face = RectangleRounded(w, l, max(r, 1e-3)).face() if r > 1e-3 else Face.make_rect(w, l)
    return Pos(0, 0, z0) * Solid.extrude(face, Vector(0, 0, z1 - z0))


def offset_prism(p: Preset, d: float, z0: float, z1: float) -> Solid:
    """Phone outline offset by d (may be negative), as a prism."""
    return rrect_prism(p.W + 2 * d, p.L + 2 * d, p.body.corner_radius + d, z0, z1)


def offset_frustum(p: Preset, d0: float, z0: float, d1: float, z1: float) -> Solid:
    """Ruled loft between the phone outline offset by d0 at z0 and offset by d1 at z1.
    |d1-d0| == |z1-z0| gives an exact 45 degree wall (support-free overhang)."""
    def wire(d, z):
        w, l = p.W + 2 * d, p.L + 2 * d
        r = safe_corner_radius(p.body.corner_radius + d, w, l)
        return (Pos(0, 0, z) * RectangleRounded(w, l, max(r, 1e-3)).face()).outer_wire()
    return Solid.make_loft([wire(d0, z0), wire(d1, z1)], ruled=True)


def _is_valid(s) -> bool:
    return bool(s.is_valid) and s.volume > 1e-6


def _top_face_outer_edges(solid: Solid, z: float):
    return [e for e in solid.edges() if abs(e.center().Z - z) < 1e-4
            and abs(e.bounding_box().min.Z - e.bounding_box().max.Z) < 1e-6]


def place_on_edge(local: Solid, p: Preset, side: str, along: float, z: float) -> Solid:
    """`local` is modelled with +X = outward, X=0 on the cavity wall, Y centred on the feature.
    `along` = world coordinate along the edge (Y for left/right, X for top/bottom)."""
    ang = SIDE_ANGLE[side]
    half_w, half_l = p.W / 2 + p.o, p.L / 2 + p.o
    if side == "right":   pt = (half_w, along)
    elif side == "left":  pt = (-half_w, along)
    elif side == "top":   pt = (along, half_l)
    else:                 pt = (along, -half_l)
    return Pos(pt[0], pt[1], z) * Rot(0, 0, ang) * local


def button_along(p: Preset, b) -> float:
    if b.side in ("left", "right"):
        return p.L / 2 - b.pos - b.length / 2
    return -p.W / 2 + b.pos + b.length / 2


def button_zc(p: Preset) -> float:
    return p.bp_t + p.T / 2


# ----------------------------------------------------------------------------- button parts
def _button_local(p: Preset, b) -> dict:
    """Return dict of button solids in local coords (+X outward, X=0 at cavity wall)."""
    s, c = p.style, p.clearances
    bh, L = s.button_height, b.length
    fo, ft, trav = s.button_flange_overhang, s.button_flange_thickness, s.button_travel
    pd = ft + trav                      # pocket depth into TPU wall
    w = s.frame_wall
    cap_h = s.button_cap_height
    cap_ov = 0.2
    # at rest the button is pushed OUT: flange bears on pocket ceiling at x = pd
    flange = Pos((pd - ft / 2), 0, 0) * Box(ft, L + 2 * fo, bh + 2 * fo)
    flange = safe_chamfer(flange, [e for e in flange.edges()
                                   if abs(e.center().X - pd) < 1e-4 and e.is_closed is not None
                                   and abs(e.bounding_box().min.X - e.bounding_box().max.X) < 1e-6],
                          0.35, limit=ft)
    body_x0, body_x1 = pd - 0.01, w + trav
    body = Pos((body_x0 + body_x1) / 2, 0, 0) * Box(body_x1 - body_x0, L, bh)
    cap = Pos(w + trav + cap_h / 2, 0, 0) * Box(cap_h, L + 2 * cap_ov, bh + 2 * cap_ov)
    cap = safe_fillet(cap, [e for e in cap.edges()
                            if abs(e.center().X - (w + trav + cap_h)) < 1e-4], 0.35, limit=cap_h)
    plunger_len = p.o + trav - 0.05
    plunger = Pos(trav - plunger_len / 2, 0, 0) * Box(plunger_len, max(L * 0.5, 2), max(bh * 0.5, 1.5))
    # plunger sits on the flange's inner face: flange inner face is at x = pd - ft = trav
    btn = flange.fuse(body, cap, plunger).clean()
    return {"button": btn, "pd": pd, "bh": bh}


def button_print_shape(p: Preset, b) -> Solid:
    """Single button, cap face down on the bed (local +X outward -> -Z), grounded."""
    return orient_for_print(_button_local(p, b)["button"], rot=(0, 90, 0))


def generate_buttons(p: Preset) -> list[tuple[str, Solid]]:
    """Buttons in DESIGN pose (assembled, pushed out). Returns [(id, solid)] (memoised)."""
    def build():
        out = []
        for b in p.buttons:
            loc = _button_local(p, b)["button"]
            out.append((b.id, place_on_edge(loc, p, b.side, button_along(p, b), button_zc(p))))
        return out
    return list(_memo(part_key(p, "buttons"), build))


def buttons_print_layout(p: Preset) -> list:
    """Every button in print pose (cap down), laid out in a row along X: the Buttons part (memoised)."""
    if not p.buttons:
        return []
    return list(_memo("print-" + part_key(p, "buttons"),
                      lambda: layout_row([button_print_shape(p, b) for b in p.buttons])))


# ----------------------------------------------------------------------------- frame
def _frame_outer(p: Preset) -> Solid:
    """Outer envelope of the bumper (and of the unibody): outline prism with rounded rims."""
    s = p.style
    outer = offset_prism(p, p.outer_offset, 0, p.H)
    # rounded front rim (screen-protecting lip edge)
    outer = safe_fillet(outer, _top_face_outer_edges(outer, p.H), 0.8, limit=s.frame_wall)
    outer = safe_fillet(outer, _top_face_outer_edges(outer, 0.0), 0.4, limit=s.frame_wall)
    return outer


def _cavity_and_lip_cuts(p: Preset, cavity_z0: float) -> list[Solid]:
    """Phone cavity from `cavity_z0` up, the 45 deg ramp under the screen lip, screen opening."""
    s = p.style
    l_ramp = p.cavity_offset + s.front_lip
    cavity_top = p.H - p.lip_t                    # z where the lip ramp starts
    return [
        offset_prism(p, p.cavity_offset, cavity_z0, cavity_top + EPS),            # phone cavity
        offset_frustum(p, p.cavity_offset, cavity_top, -s.front_lip, cavity_top + l_ramp),
        offset_prism(p, -s.front_lip, cavity_top + l_ramp - EPS, p.H + 1),        # screen opening
    ]


def _port_cutters(p: Preset) -> list[Solid]:
    zc = p.bp_t + p.T / 2
    cuts = []
    for pt in p.ports:
        rad = safe_corner_radius(pt.radius, pt.width, pt.height)
        prof = RectangleRounded(pt.width, pt.height, max(rad, 1e-3)).face()
        cutter = Solid.extrude(prof, Vector(0, 0, 8))          # along +Z, local sketch XY
        # re-orient: sketch plane XY -> (along, vertical), extrusion -> outward (+X local)
        loc = Location(Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))
        cutter = loc * cutter                                  # extrusion now +X, sketch x->Y, y->Z
        cutter = Pos(-1.0, 0, 0) * cutter                      # begin slightly inside cavity
        cuts.append(place_on_edge(cutter, p, pt.side, pt.center, zc + pt.z_offset))
    return cuts


def generate_frame(p: Preset) -> Solid:
    """TPU bumper frame (memoised: it does not depend on the camera or the backplate pattern)."""
    return _memo(part_key(p, "frame"), lambda: _build_frame(p))


def _build_frame(p: Preset) -> Solid:
    s = p.style
    bp_t = p.bp_t
    outer = _frame_outer(p)
    gz0 = bp_t - s.tongue_height - p.sc               # groove bottom
    gz1 = bp_t + p.sc                                  # groove top
    # Print orientation is BACK-DOWN (z=0 on the bed, printing towards the screen lip), so every
    # inward step going +Z must be a 45 deg ramp, never a flat ceiling:
    #   * groove ceiling  : groove_offset -> cavity_offset ramp above the groove
    #   * screen lip      : cavity_offset -> -front_lip ramp under the lip
    g_ramp = p.groove_offset - p.cavity_offset
    cuts = [
        offset_prism(p, p.rear_opening_offset, -1, gz0 + EPS),               # rear opening
        offset_prism(p, p.groove_offset, gz0, gz1),                          # retention groove
        offset_frustum(p, p.groove_offset, gz1 - EPS, p.cavity_offset, gz1 - EPS + g_ramp),
    ]
    cuts += _cavity_and_lip_cuts(p, gz0)
    cuts += _port_cutters(p)
    # button windows + flange pockets
    c = p.clearances.button_clearance
    for b in p.buttons:
        bh = s.button_height
        pd = s.button_flange_thickness + s.button_travel
        window = Pos(s.frame_wall / 2 + 0.5, 0, 0) * Box(s.frame_wall + 1.0 + 1.0, b.length + 2 * c, bh + 2 * c)
        fo = s.button_flange_overhang
        pocket = Pos((pd - 0.5) / 2, 0, 0) * Box(pd + 0.5, b.length + 2 * fo + 2 * c, bh + 2 * fo + 2 * c)
        cuts.append(place_on_edge(window, p, b.side, button_along(p, b), button_zc(p)))
        cuts.append(place_on_edge(pocket, p, b.side, button_along(p, b), button_zc(p)))
    frame = outer
    for cutter in cuts:
        frame = frame.cut(cutter)
    frame = frame.clean()
    if not _is_valid(frame):
        raise RuntimeError("frame solid invalid")
    return frame


# ----------------------------------------------------------------------------- backplate
def _rr_wire(w, h, r, ox, oy, z):
    r = safe_corner_radius(r, w, h)
    return (Pos(ox, oy, z) * RectangleRounded(w, h, max(r, 0.05)).face()).outer_wire()


def camera_aperture_cutters(p: Preset, z_outer: float, z_base: float) -> list[Solid]:
    """Camera aperture cutters, centred on the island: the outer-face profile at z_outer, the
    island base (+ aperture margin) at z_base, ruled-lofted in between when they differ (optional
    camera.opening), and extended 1 mm past both faces so the cut is clean."""
    base, outer = p.aperture_profiles()
    if outer == base:
        return [rrect_prism(base[0], base[1], base[2], z_outer - 1.0, z_base + 1.0)]
    loft = Solid.make_loft([_rr_wire(*outer, z_outer), _rr_wire(*base, z_base)], ruled=True)
    if not _is_valid(loft):
        raise ParamError("camera.opening produced an invalid aperture loft; check its size and offset")
    below = Pos(outer[3], outer[4], 0) * rrect_prism(outer[0], outer[1], outer[2], z_outer - 1.0, z_outer + EPS)
    above = rrect_prism(base[0], base[1], base[2], z_base - EPS, z_base + 1.0)
    return [below, loft, above]


def generate_backplate(p: Preset, with_pattern: bool = True):
    """Returns the plate solid (or (plate, inlay) tuple when with_pattern)."""
    s = p.style
    th = s.tongue_height
    body = offset_prism(p, p.plate_body_offset, 0, p.bp_t - th + EPS)
    tongue = offset_prism(p, p.tongue_offset, 0, th)
    # 45deg lead-in on the FRONT (inner) face so the tongue rides over the TPU lip; the rear
    # face stays a flat shoulder that bears against the lip when pulled.
    top_edges = _top_face_outer_edges(tongue, th)
    tongue = safe_chamfer(tongue, top_edges, 0.4, limit=th)
    tongue = Pos(0, 0, p.bp_t - th) * tongue
    plate = body.fuse(tongue).clean()
    cx, cy = p.camera_center()
    if p.camera.ring:
        w, h, r = camera_cutout_dims(p)
        plate = plate.cut(rrect_prism(w, h, r, -1, p.bp_t + 1).moved(Location((cx, cy, 0))))
        # catch groove for the camera-ring snap bead (open to the inner face)
        g = 2 * (p.style.camera_bead - p.clearances.camera_ring_clearance + 0.05)   # per-side growth beyond cutout
        gz0 = p.bp_t - 0.5 - 0.05
        plate = plate.cut(rrect_prism(w + g + 0.0, h + g, r + g / 2, gz0, p.bp_t + 1).moved(Location((cx, cy, 0))))
    else:
        plate = _keep_main_solid(plate.cut(_prisms(camera_cutout_poly(p), -1.0, p.bp_t + 2.0)), "backplate")
    if s.magsafe_ring:
        z0 = p.bp_t - s.magsafe_depth
        plate = plate.cut(_magsafe_tool(p, z0, s.magsafe_depth + 0.5)).clean()
    if not _is_valid(plate):
        raise RuntimeError("backplate invalid")
    if with_pattern:
        return apply_backplate_pattern(plate, p)
    return plate


# ----------------------------------------------------------------------------- patterns
# The 2D pattern library (generators, border/rounding finishing, connectivity, text/SVG)
# lives in patterns.py; this module turns its cut-outs into B-rep.
def _poly_to_face(poly: Polygon) -> Face:
    def wire(coords):
        pts = [Vector(x, y, 0) for x, y in list(coords)[:-1]]
        return Wire.make_polygon(pts, close=True)
    return Face(wire(poly.exterior.coords), [wire(i.coords) for i in poly.interiors])


CUT_TOL = 0.02   # mm: cut tools follow the 2D outlines this closely (far below FDM or laser resolution)


def _thin(poly: Polygon) -> Polygon:
    """The outline with near-collinear vertices dropped (deviation <= CUT_TOL). Text glyphs, SVG
    art and sampled curves arrive with ~10x more vertices than the shape needs, and every vertex
    becomes a B-rep face of the cut (text: 2.9 s -> 0.2 s). Corners and stencil bridges stay; the
    2D geometry (checks, preview, laser SVG) is untouched."""
    g = poly.simplify(CUT_TOL, preserve_topology=True)
    return g if g.geom_type == "Polygon" and g.is_valid and not g.is_empty else poly


def _cell_face(c: Cell, shrink: float = 0.0) -> Face | None:
    """B-rep face of one cut-out (optionally shrunk, for inlay clearance). Exact circles become
    true circles: one cylindrical side face instead of dozens of facets."""
    if c.circle is not None:
        x, y, r = c.circle
        r -= shrink
        return Pos(x, y, 0) * Circle(r).face() if r > 0.05 else None
    if shrink <= 0:
        return _poly_to_face(_thin(c.poly))
    return [_poly_to_face(_thin(g)) for g in _parts_of(c.poly.buffer(-shrink))
            if g.geom_type == "Polygon" and g.area > 0.1] or None


def _parts_of(geom) -> list:
    return [] if geom.is_empty else (list(geom.geoms) if hasattr(geom, "geoms") else [geom])


def _magsafe_tool(p: Preset, z0: float, h: float):
    """Cutter for the MagSafe magnet pocket, from z0 up by h. magsafe_pocket_poly() validates the
    ring position first (it raises if the camera or the plate edge would trim the ring). An
    untrimmed ring is cut with true circles: two cylindrical faces instead of ~400 facets, and
    about 0.3 s faster. A ring trimmed within the allowed 0.5 % keeps the polygonal pocket."""
    from patterns import MAGSAFE_R_IN, MAGSAFE_R_OUT, MAGSAFE_TAIL, magsafe_ring_poly
    pocket = magsafe_pocket_poly(p)
    if abs(pocket.area - magsafe_ring_poly(p).area) > 1e-6:
        return _prisms(pocket, z0, h)
    oy = p.style.magsafe_offset_y
    ring = (Solid.extrude(Circle(MAGSAFE_R_OUT).face(), Vector(0, 0, h))
            .cut(Solid.extrude(Circle(MAGSAFE_R_IN).face(), Vector(0, 0, h))))
    x0, y0, x1, y1 = MAGSAFE_TAIL
    tail = Pos((x0 + x1) / 2, (y0 + y1) / 2, h / 2) * Box(x1 - x0, y1 - y0, h)
    return Pos(0, oy, z0) * Compound([ring, tail])


def _prisms(geom, z0: float, h: float):
    """Prism tool(s) of the polygon parts of a 2D shapely geometry, from z0 up by h."""
    tools = [Pos(0, 0, z0) * Solid.extrude(_poly_to_face(g), Vector(0, 0, h)) for g in _polys(geom)]
    return tools[0] if len(tools) == 1 else Compound(tools)


def _keep_main_solid(shape, name: str):
    """After a cut that may leave numeric slivers (polygonal 2D tools against exact B-rep arcs),
    keep the main solid. Anything bigger than a sliver means the geometry really split: raise."""
    solids = list(shape.solids())
    if len(solids) <= 1:
        return shape
    main = max(solids, key=lambda s: s.volume)
    stray = sum(s.volume for s in solids if s is not main)
    if stray > 0.5:
        raise RuntimeError(f"{name}: the camera cut-out split off {stray:.1f} mm3 of material")
    return main


def apply_backplate_pattern(plate: Solid, p: Preset):
    """2D first (patterns.py), then ONE extrusion batch + ONE cut. Returns (plate, inlay).
    Through-cuts that would detach material are rejected (ParamError) before any 3D work."""
    pat = p.pattern
    cells = pattern_cells(p)
    if not cells:
        return plate, None
    if pat.mode == "through":
        check_through_cut(p, [c.poly for c in cells])
    if pat.mode == "through":
        z0, h = -1.0, p.bp_t + 2.0
    else:
        z0, h = -1.0, pat.depth + 1.0           # cutter starts below outer face, depth = pat.depth
    tools = [Pos(0, 0, z0) * Solid.extrude(_cell_face(c), Vector(0, 0, h)) for c in cells]
    cutter = Compound(tools)
    result = plate.cut(cutter).clean()
    if not _is_valid(result):
        raise RuntimeError("pattern cut produced invalid solid")
    if pat.mode == "through" and len(result.solids()) > 1:
        # backstop: the 2D check above should already have rejected this
        raise ParamError(f"Through-cut pattern split the backplate into {len(result.solids())} pieces. "
                         "Increase the material web width, enable stencil bridges, or switch to deboss.")
    inlay = None
    if pat.mode == "inlay":
        faces = []
        for c in cells:
            f = _cell_face(c, shrink=p.sc / 2)
            if f is not None:
                faces.extend(f if isinstance(f, list) else [f])
        inl = [Solid.extrude(f, Vector(0, 0, pat.depth)) for f in faces]
        inlay = Compound(inl) if inl else None
    return result, inlay


def laser_polys(p: Preset):
    """Return (outline_polygon_with_holes) for the flat laser-cut backplate."""
    outline = plate_outline_poly(p, p.tongue_offset)
    holes = camera_cutout_poly(p)
    shape = outline.difference(holes)
    if p.pattern.type != "solid" and p.pattern.mode == "through":
        shape = shape.difference(unary_union([g for g in pattern_polys(p)]))
    return shape


def laser_svg(p: Preset, path: Path) -> Path:
    Path(path).write_text(laser_svg_text(p), encoding="utf-8")
    return Path(path)


def laser_svg_text(p: Preset) -> str:
    """Laser_Backplate.svg contents: closed 1:1 mm paths of the flat backplate, back view."""
    shape = laser_polys(p)
    geoms = [g for g in _parts_of(shape) if g.geom_type == "Polygon"]
    minx, miny, maxx, maxy = shape.bounds
    pad = 1.0
    wmm, hmm = maxx - minx + 2 * pad, maxy - miny + 2 * pad

    def ring(coords):
        pts = [f"{maxx - x + pad:.3f},{maxy - y + pad:.3f}" for x, y in coords]   # x mirrored: BACK view
        return "M" + " L".join(pts) + " Z"

    d = " ".join(ring(g.exterior.coords) + " " + " ".join(ring(i.coords) for i in g.interiors) for g in geoms)
    svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{wmm:.3f}mm" height="{hmm:.3f}mm" '
           f'viewBox="0 0 {wmm:.3f} {hmm:.3f}">\n'
           f'  <path d="{d}" fill="none" stroke="#ff0000" stroke-width="0.1" fill-rule="evenodd"/>\n</svg>\n')
    return svg


# ----------------------------------------------------------------------------- camera ring
def generate_camera_ring(p: Preset) -> Solid | None:
    """Press-fit camera ring, or None for an open camera cut-out (camera.ring = False). Memoised."""
    if not p.camera.ring:
        return None
    return _memo(part_key(p, "ring"), lambda: _build_camera_ring(p))


def _build_camera_ring(p: Preset) -> Solid:
    s = p.style
    cx, cy = p.camera_center()
    cw, ch, cr = camera_cutout_dims(p)                        # plate cutout
    sc = p.clearances.camera_ring_clearance
    sw, sh, sr = cw - 2 * sc, ch - 2 * sc, cr - sc            # spigot outline
    bz = s.camera_bezel_height
    bw = s.camera_bezel_width
    flange = rrect_prism(cw + 2 * bw, ch + 2 * bw, cr + bw, -bz, 0.0)
    flange = safe_fillet(flange, _top_face_outer_edges(flange, -bz), 0.6, limit=bz)
    spigot = rrect_prism(sw, sh, sr, -EPS, p.bp_t)
    bead = rrect_prism(sw + 2 * s.camera_bead, sh + 2 * s.camera_bead, sr + s.camera_bead, p.bp_t - 0.5, p.bp_t)
    bead = safe_chamfer(bead, _top_face_outer_edges(bead, p.bp_t), 0.3, limit=0.5)
    ring = flange.fuse(spigot, bead)
    for cutter in camera_aperture_cutters(p, -bz, p.bp_t):
        ring = ring.cut(cutter)
    # relief slots (4) so the bead can flex
    slot = 0.6
    for sx, sy, sz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
        if sx:
            cutter = Pos(sx * (sw / 2), 0, p.bp_t - 1.5) * Box(6, slot, 3)
        else:
            cutter = Pos(0, sy * (sh / 2), p.bp_t - 1.5) * Box(slot, 6, 3)
        ring = ring.cut(cutter)
    ring = ring.clean()
    ring = Pos(cx, cy, 0) * ring
    if not _is_valid(ring):
        raise RuntimeError("camera ring invalid")
    return ring


# ----------------------------------------------------------------------------- orientation
def _bottom_contact_area(shape, tol=1e-3) -> tuple[float, float]:
    bb = shape.bounding_box()
    area = 0.0
    for f in shape.faces():
        if f.geom_type.name != "PLANE":
            continue
        n = f.normal_at()
        if n.Z < -0.999 and abs(f.bounding_box().max.Z - bb.min.Z) < tol:
            area += f.area
    return area, bb.max.Z - bb.min.Z


_ROTS = [(0, 0, 0), (180, 0, 0), (90, 0, 0), (-90, 0, 0), (0, 90, 0), (0, -90, 0)]


def print_offset(shape, ref=None, center_xy: bool = True) -> tuple[float, float, float]:
    """Translation that grounds `shape` (as-is, no rotation) at Z=0 centred in XY; with `ref`,
    the translation that grounds `ref` (co-registered parts such as plate + inlay)."""
    bb = (ref if ref is not None else shape).bounding_box()
    cx = (bb.min.X + bb.max.X) / 2 if center_xy else 0.0
    cy = (bb.min.Y + bb.max.Y) / 2 if center_xy else 0.0
    return (-cx, -cy, -bb.min.Z)


def orient_for_print(shape, center_xy: bool = True, rot=None, ref=None):
    """Orient a part for FDM and ground it at Z=0, centred in XY.
    `rot` = explicit (rx, ry, rz) chosen per part for support-free printing (frame: lip down,
    plate: outer face down, ring: bezel down, button: cap down). Without it, falls back to the
    axis-aligned orientation with the largest flat bed contact (tie-break: lowest height)."""
    if rot is not None and tuple(rot) == (0, 0, 0):       # common case: a pure translation
        return Pos(*print_offset(shape, ref, center_xy)) * shape
    best = None
    for r in ([rot] if rot is not None else _ROTS):
        cand = Rot(*r) * shape
        area, height = _bottom_contact_area(cand)
        key = (round(area, 1), -height)
        if best is None or key > best[0]:
            best = (key, cand)
    out = best[1]
    # `ref`: ground/centre using ANOTHER shape (same rotation) so co-registered parts (plate+inlay)
    # keep their relative position.
    rref = (Rot(*(rot if rot is not None else (0, 0, 0))) * ref) if ref is not None else None
    return Pos(*print_offset(out, rref, center_xy)) * out


def layout_row(shapes: list, gap: float = 6.0):
    """Place already-oriented shapes in a row along X (no overlaps)."""
    x = 0.0
    out = []
    for s in shapes:
        bb = s.bounding_box()
        out.append(Pos(x - bb.min.X, -(bb.min.Y + bb.max.Y) / 2, 0) * s)
        x += (bb.max.X - bb.min.X) + gap
    return out


# ----------------------------------------------------------------------------- export
def _label(shape, name):
    shape.label = name
    return shape


def build_case_parts(p: Preset) -> dict:
    """All modular parts in design pose and print pose. Single source for preview, export and
    3MF fixtures, so the preview always shows exactly what is exported."""
    timings = {}

    def timed(name, fn):
        t = time.perf_counter()
        v = fn()
        timings[name] = round(time.perf_counter() - t, 3)
        return v

    frame = timed("frame", lambda: generate_frame(p))
    plate, inlay = timed("backplate", lambda: generate_backplate(p))
    ring = timed("camera_ring", lambda: generate_camera_ring(p))        # None: open camera cut-out
    btns = timed("buttons", lambda: generate_buttons(p))
    # every part prints in its design orientation, so its print pose is a pure translation
    # (frame BACK-DOWN with the lip printing last, plate and inlay outer face down, ring bezel down)
    offsets = {"Frame_TPU": print_offset(frame), "Backplate_PLA": print_offset(plate)}
    if ring is not None:
        offsets["CameraRing"] = print_offset(ring)
    if inlay is not None:
        offsets["Backplate_Inlay"] = offsets["Backplate_PLA"]          # co-registered with the plate
    src = {"Frame_TPU": frame, "Backplate_PLA": plate, "CameraRing": ring, "Backplate_Inlay": inlay}
    oriented = {name: Pos(*off) * src[name] for name, off in offsets.items() if name != "Backplate_Inlay"}
    if btns:
        oriented["Buttons"] = Compound(buttons_print_layout(p), label="Buttons")
    if inlay is not None:
        oriented["Backplate_Inlay"] = Pos(*offsets["Backplate_Inlay"]) * inlay
    design = {"frame": frame, "plate": plate, "inlay": inlay, "ring": ring, "buttons": btns}
    return {"design": design, "oriented": oriented, "offsets": offsets, "timings": timings}


def export_set(p: Preset, out_dir: str | Path, printer=None) -> dict:
    """Build all parts, write STL+STEP per part, Full_Assembly.step, Laser_Backplate.svg, the
    3MF set laid out on the selected printer's plate (BedOverflow if it does not fit), the
    print-in-place 3MF + gap report (toolchanger printers only) and the verified unibody."""
    import bambu_3mf
    from printers import PrinterProfile, get_printer
    pr = printer if isinstance(printer, PrinterProfile) else get_printer(printer)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    built = build_case_parts(p)
    parts, d = built["oriented"], built["design"]
    files = [bambu_3mf.write_set_3mf(out / "Case_Set.3mf", parts, printer=pr)]   # fails fast on bed overflow
    if d["inlay"] is not None:
        files.append(bambu_3mf.write_backplate_multicolor_3mf(out / "Backplate_Multicolor.3mf", parts, printer=pr))
    for name, shape in parts.items():
        shape.label = name
        stl, step = out / f"{name}.stl", out / f"{name}.step"
        export_stl(shape, str(stl), tolerance=0.01, angular_tolerance=0.1)
        if not export_step(shape, str(step)):
            raise RuntimeError(f"STEP export failed: {name}")
        files += [stl, step]

    asm_children = [_label(d["frame"], "Frame"), _label(d["plate"], "Backplate")]
    if d["ring"] is not None:
        asm_children.append(_label(d["ring"], "CameraRing"))
    asm_children += [_label(b, f"Button_{n}") for n, b in d["buttons"]]
    asm = Compound(asm_children, label="Full_Assembly")
    asm_path = out / "Full_Assembly.step"
    if not export_step(asm, str(asm_path)):
        raise RuntimeError("assembly STEP failed")
    files.append(asm_path)
    files.append(laser_svg(p, out / "Laser_Backplate.svg"))
    pip = None
    if pr.toolchanger:
        import print_in_place
        files.append(bambu_3mf.write_toolchanger_3mf(out / "Toolchanger_InPlace.3mf", d, parts, printer=pr))
        pip = print_in_place.pip_report(p, d)
        files.append(print_in_place.write_report(pip, out / "PrintInPlace_Report.txt"))
    unibody = print_ready_unibody(p)
    unibody_stl = out / "Unibody_OnePiece.stl"
    export_stl(unibody, str(unibody_stl), tolerance=0.01, angular_tolerance=0.1)
    files.append(unibody_stl)
    return {"files": files, "timings": built["timings"], "design": d, "oriented": parts, "printer": pr, "pip": pip}


def print_ready_unibody(p: Preset) -> Solid:
    """Unibody in print pose (rear face on Z=0), verified as ONE watertight, void-free,
    self-intersection-free body before it is handed to any exporter."""
    import verify
    u = orient_for_print(generate_unibody(p), rot=(0, 0, 0))
    verify.assert_one_piece(u, "Unibody_OnePiece")
    u.label = "Unibody_OnePiece"
    return u


def unibody_adaptations(p: Preset) -> list[str]:
    """Features the single-material unibody cannot reproduce from the modular design, and what it
    does instead. Shown to the user (preview findings, export README) -- never applied silently."""
    notes = ["Unibody: the backplate is a solid floor moulded into the bumper (no snap joint); "
             "the phone is stretched in through the screen opening."]
    if p.buttons:
        notes.append("Unibody: floating buttons are replaced by raised TPU button covers with an inner "
                     "press nub (single material cannot hold a captured moving part).")
    if p.camera.ring:
        notes.append("Unibody: the camera surround is flush with the back (a raised bezel would lift the "
                     "case off the bed when printing back-down); use the modular camera ring for a raised guard.")
    else:
        notes.append("Unibody: the open camera cut-out goes straight through the floor, like the modular "
                     "backplate (this device has no camera ring).")
    if p.pattern.type != "solid" and p.pattern.mode == "inlay":
        notes.append("Unibody: the 2-color inlay is exported as a deboss recess (single material).")
    return notes


def _button_cover_local(p: Preset, b) -> Solid:
    """Unibody button: raised pad on the outer wall + inner press nub, local coords (+X outward,
    X=0 on the cavity wall). Overlaps the wall so it fuses as one body. The pad underside gets a
    45 deg chamfer so it prints support-free back-down."""
    s = p.style
    w, bh, L, cap_h, ov = s.frame_wall, s.button_height, b.length, s.button_cap_height, 0.2
    x0 = w - 0.2                                       # 0.2 mm into the wall: real overlap, no seam
    pad = Pos((x0 + w + cap_h) / 2, 0, 0) * Box(w + cap_h - x0, L + 2 * ov, bh + 2 * ov)
    bottom_outer = [e for e in pad.edges()
                    if abs(e.center().X - (w + cap_h)) < 1e-4 and abs(e.center().Z + bh / 2 + ov) < 1e-4]
    pad = safe_chamfer(pad, bottom_outer, cap_h - 0.05, limit=cap_h * 2.2)
    nub_len = p.o - 0.05                               # stops 0.05 mm short of the phone body
    if nub_len >= 0.1:
        nub = Pos((0.2 - nub_len) / 2, 0, 0) * Box(nub_len + 0.2, max(L * 0.5, 2), max(bh * 0.5, 1.5))
        pad = pad.fuse(nub)
    return pad.clean()


def generate_unibody(p: Preset) -> Solid:
    """Single-piece unibody print (single-material TPU or other flexible filament), design pose,
    rear face at Z=0 (= print orientation, back-down).

    Built as ONE body from first principles -- the bumper envelope with a solid floor where the
    backplate would be -- rather than fusing separately-toleranced parts. The modular generators
    are untouched. See `unibody_adaptations()` for features that change in this mode."""
    import copy
    q = copy.deepcopy(p)
    if q.pattern.mode == "inlay":
        q.pattern.mode = "deboss"            # explicit adaptation, reported by unibody_adaptations()
    cuts = _cavity_and_lip_cuts(q, q.bp_t) + _port_cutters(q)
    if q.camera.ring:
        cx, cy = q.camera_center()
        cuts += [Pos(cx, cy, 0) * t for t in camera_aperture_cutters(q, 0.0, q.bp_t)]
    else:
        # open cut-out through the floor, stopping just inside the cavity wall so the side walls
        # stay whole (an edge-to-edge camera plateau passes between them)
        hole = camera_cutout_poly(q).intersection(plate_outline_poly(q, q.cavity_offset - 0.1))
        cuts.append(_prisms(hole, -1.0, q.bp_t + 1.0 + EPS))
    body = _frame_outer(q)
    for cutter in cuts:
        body = body.cut(cutter)
    for b in q.buttons:
        body = body.fuse(place_on_edge(_button_cover_local(q, b), q, b.side, button_along(q, b), button_zc(q)))
    if q.style.magsafe_ring:                 # magnets drop into the floor from the phone side
        body = body.cut(_magsafe_tool(q, q.bp_t - q.style.magsafe_depth, q.style.magsafe_depth + 0.5))
    body = body.clean()
    body, _ = apply_backplate_pattern(body, q)
    if not _is_valid(body):
        raise RuntimeError("unibody solid invalid")
    if len(body.solids()) != 1:
        raise RuntimeError(f"unibody is not one piece: {len(body.solids())} separate solids")
    body = body.solids()[0]
    if len(body.shells()) != 1:
        raise RuntimeError(f"unibody has {len(body.shells()) - 1} sealed internal void(s)")
    return body


# ----------------------------------------------------------------------------- fit-test coupon
def _solids_of(r):
    if r is None:
        return None
    if isinstance(r, (list, tuple)) or r.__class__.__name__ == "ShapeList":
        items = [s for x in r for s in (x.solids() if hasattr(x, "solids") else [x])]
    else:
        items = list(r.solids())
    if not items:
        return None
    return items[0] if len(items) == 1 else Compound(items)


def coupon_region(p: Preset, margin: float = 4.0, min_span: float = 30.0):
    """Corner (nearest the camera) region holding: the whole camera-ring interface, the same-side
    button closest to the camera, and >= min_span mm of straight frame<->backplate snap joint.
    With an open camera cut-out (no ring) the region is the corner of the cut-out nearest the
    camera's side: at most 40 mm wide, so a full-width camera plateau still gives a short print.
    Returns dict(x0,x1,y0,y1,sx,button)."""
    cx, cy = p.camera_center()
    minx, miny, maxx, maxy = camera_cutout_poly(p).bounds
    bez = p.style.camera_bezel_width if p.camera.ring else 0.0
    sx = 1 if cx >= 0 else -1
    side = "right" if sx > 0 else "left"
    cands = [b for b in p.buttons if b.side == side]
    btn = min(cands, key=lambda b: abs(button_along(p, b) - cy)) if cands else None
    outer = p.outer_offset
    x_edge, y_edge = sx * (p.W / 2 + outer + 1), p.L / 2 + outer + 1
    x_in = (minx - bez - margin) if sx > 0 else (maxx + bez + margin)
    if not p.camera.ring and abs(x_edge - x_in) > 40.0:
        x_in = x_edge - sx * 40.0
    y_lo = miny - bez - margin
    if btn is not None:
        by = button_along(p, btn)
        y_lo = min(y_lo, by - btn.length / 2 - margin)
    y_lo = min(y_lo, y_edge - min_span)
    if abs(x_edge - x_in) < min_span:
        x_in = x_edge - sx * min_span
    return {"x0": min(x_in, x_edge), "x1": max(x_in, x_edge), "y0": y_lo, "y1": y_edge, "sx": sx, "button": btn}


COUPON_TYPES = ("camera", "buttons", "ports")


def _cut(shape, x0, x1, y0, y1, h):
    """Keep the part of `shape` inside the XY rectangle (full height). Real generator geometry,
    only trimmed -- dimensional relationships are untouched."""
    box = Pos((x0 + x1) / 2, (y0 + y1) / 2, h / 2) * Box(x1 - x0, y1 - y0, h + 10)
    return _solids_of(shape.intersect(box))


def _coupon_camera(q: Preset) -> dict:
    """Camera & snap-fit coupon (the original default): camera corner of frame + backplate,
    the whole camera ring, and the same-side button nearest the camera."""
    reg = coupon_region(q)
    frame = _cut(generate_frame(q), reg["x0"], reg["x1"], reg["y0"], reg["y1"], q.H)
    plate = _cut(generate_backplate(q, with_pattern=False), reg["x0"], reg["x1"], reg["y0"], reg["y1"], q.H)
    ring = generate_camera_ring(q)                    # None: open camera cut-out
    oriented = {
        "Frame_TPU_coupon": orient_for_print(frame, rot=(0, 0, 0)),
        "Backplate_PLA_coupon": orient_for_print(plate, rot=(0, 0, 0)),
    }
    if ring is not None:
        oriented["CameraRing"] = orient_for_print(ring, rot=(0, 0, 0))
    btn = None
    if reg["button"] is not None:
        b = reg["button"]
        btn = (b.id, place_on_edge(_button_local(q, b)["button"], q, b.side, button_along(q, b), button_zc(q)))
        oriented[f"Button_{b.id}"] = button_print_shape(q, b)
    design = {"frame": frame, "plate": plate, "ring": ring, "button": btn}
    return {"region": reg, "span": (reg["x1"] - reg["x0"], reg["y1"] - reg["y0"]),
            "design": design, "oriented": oriented}


def _edge_strip(q: Preset, side: str, a0: float, a1: float, depth: float = 8.0):
    """XY rectangle covering `side`'s bumper wall between along-edge coords a0..a1 (world X for
    top/bottom, world Y for left/right), reaching `depth` mm inside the phone outline."""
    ow, ol = q.W / 2 + q.outer_offset + 1, q.L / 2 + q.outer_offset + 1
    if side == "right":
        return q.W / 2 - depth, ow, a0, a1
    if side == "left":
        return -ow, -q.W / 2 + depth, a0, a1
    if side == "top":
        return a0, a1, q.L / 2 - depth, ol
    return a0, a1, -ol, -q.L / 2 + depth


def _coupon_buttons(q: Preset, margin: float = 4.0) -> dict:
    """Button-fit coupon: for every side carrying buttons, the bumper wall strip with the real
    windows + flange pockets, the matching backplate edge (snapped in, it holds the wall at its
    real stiffness and position), plus every button on that side."""
    if not q.buttons:
        raise ParamError("This device preset has no buttons; choose the camera or ports coupon.")
    frame = generate_frame(q)
    plate = generate_backplate(q, with_pattern=False)
    oriented, design, spans = {}, {"frames": {}, "plates": {}, "buttons": []}, []
    s, c = q.style, q.clearances
    for side in SIDE_ANGLE:
        btns = [b for b in q.buttons if b.side == side]
        if not btns:
            continue
        grow = s.button_flange_overhang + c.button_clearance + margin
        lo = min(button_along(q, b) - b.length / 2 for b in btns) - grow
        hi = max(button_along(q, b) + b.length / 2 for b in btns) + grow
        x0, x1, y0, y1 = _edge_strip(q, side, lo, hi)
        piece = _cut(frame, x0, x1, y0, y1, q.H)
        design["frames"][side] = piece
        oriented[f"Frame_TPU_buttons_{side}"] = orient_for_print(piece, rot=(0, 0, 0))
        design["plates"][side] = _cut(plate, x0, x1, y0, y1, q.H)
        oriented[f"Backplate_PLA_buttons_{side}"] = orient_for_print(design["plates"][side], rot=(0, 0, 0))
        spans.append((x1 - x0, y1 - y0))
        for b in btns:
            design["buttons"].append((b.id, place_on_edge(_button_local(q, b)["button"], q, side,
                                                          button_along(q, b), button_zc(q))))
            oriented[f"Button_{b.id}"] = button_print_shape(q, b)
    span = max(spans, key=lambda wl: wl[0] * wl[1])
    return {"region": None, "span": span, "design": design, "oriented": oriented}


def _coupon_ports(q: Preset, margin: float = 6.0) -> dict:
    """Bottom-ports coupon: the bottom bumper wall with the real charging/speaker openings and
    enough wall on either side to check their position against the phone."""
    ports = [pt for pt in q.ports if pt.side == "bottom"]
    if not ports:
        raise ParamError("This device preset has no bottom ports; choose the camera or buttons coupon.")
    half = q.W / 2 + q.outer_offset + 1
    lo = max(-half, min(pt.center - pt.width / 2 for pt in ports) - margin)
    hi = min(half, max(pt.center + pt.width / 2 for pt in ports) + margin)
    x0, x1, y0, y1 = _edge_strip(q, "bottom", lo, hi, depth=10.0)
    piece = _cut(generate_frame(q), x0, x1, y0, y1, q.H)
    plate = _cut(generate_backplate(q, with_pattern=False), x0, x1, y0, y1, q.H)
    return {"region": None, "span": (x1 - x0, y1 - y0), "design": {"frame": piece, "plate": plate},
            "oriented": {"Frame_TPU_ports_bottom": orient_for_print(piece, rot=(0, 0, 0)),
                         "Backplate_PLA_ports_bottom": orient_for_print(plate, rot=(0, 0, 0))}}


def generate_test_coupon(p: Preset, coupon_type: str | None = None) -> dict:
    """Short fit-test print cut from the REAL generator geometry (no simplified stand-ins).
    coupon_type: camera (default; camera ring + snap joint corner) | buttons | ports.
    Print time depends on your slicer settings: slice it to see the estimate."""
    import copy
    ctype = coupon_type or "camera"
    if ctype not in COUPON_TYPES:
        raise ParamError(f"coupon type must be one of {', '.join(COUPON_TYPES)}")
    q = copy.deepcopy(p)
    q.pattern.type = "solid"
    c = {"camera": _coupon_camera, "buttons": _coupon_buttons, "ports": _coupon_ports}[ctype](q)
    c.update(preset=q, coupon_type=ctype)
    return c


def export_coupon(p: Preset, out_dir, coupon_type: str | None = None, printer=None) -> dict:
    import bambu_3mf
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    c = generate_test_coupon(p, coupon_type)
    files = []
    for name, shape in c["oriented"].items():
        shape.label = name
        export_stl(shape, str(out / f"{name}.stl"), tolerance=0.01, angular_tolerance=0.1)
        export_step(shape, str(out / f"{name}.step"))
        files += [out / f"{name}.stl", out / f"{name}.step"]
    objs = [bambu_3mf.Obj(n, [bambu_3mf.part_from_shape(n, s, 1 if n.startswith("Frame") else 2)])
            for n, s in c["oriented"].items()]
    files.append(bambu_3mf.write_3mf(out / "Coupon_Set.3mf", objs, printer))
    c["files"] = files
    return c
