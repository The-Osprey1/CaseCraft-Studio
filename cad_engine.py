"""CaseCraft headless CAD engine (build123d / OpenCascade).

Public API:
    generate_frame(p), generate_backplate(p), generate_camera_ring(p), generate_buttons(p)
    apply_backplate_pattern(plate, p)  -> (plate, inlay_or_None)
    orient_for_print(shape), laser_svg(p, path), export_set(p, out_dir)
Design pose: see params.py docstring (z=0 = outer backplate face, phone at +Z).
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path

import numpy as np
from build123d import (Axis, Box, Compound, Face, Location, Plane, Pos, RectangleRounded, Rot,
                       Solid, Vector, Wire, export_step, export_stl)
from shapely import affinity, voronoi_polygons
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon, box as sbox
from shapely.ops import unary_union

from params import MIN_FLOOR, PATTERN_DEFAULT_PITCH, ParamError, Preset, wave_cos
from safe_ops import safe_chamfer, safe_corner_radius, safe_fillet

log = logging.getLogger("casecraft")
EPS = 0.01
SIDE_ANGLE = {"right": 0, "top": 90, "left": 180, "bottom": 270}


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


def rrect_poly(w: float, l: float, r: float, cx=0.0, cy=0.0) -> Polygon:
    r = max(0.0, min(r, 0.499 * min(w, l)))
    if r < 1e-3:
        return sbox(cx - w / 2, cy - l / 2, cx + w / 2, cy + l / 2)
    core = sbox(cx - w / 2 + r, cy - l / 2 + r, cx + w / 2 - r, cy + l / 2 - r)
    return core.buffer(r, quad_segs=24)


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
    """Buttons in DESIGN pose (assembled, pushed out). Returns [(id, solid)]."""
    out = []
    for b in p.buttons:
        loc = _button_local(p, b)["button"]
        out.append((b.id, place_on_edge(loc, p, b.side, button_along(p, b), button_zc(p))))
    return out


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
def camera_cutout_dims(p: Preset):
    c, s = p.camera, p.style
    m = s.camera_cutout_margin
    return c.width + 2 * m, c.height + 2 * m, c.radius + m


def plate_outline_poly(p: Preset, offset: float) -> Polygon:
    return rrect_poly(p.W + 2 * offset, p.L + 2 * offset, p.body.corner_radius + offset)


def camera_cutout_poly(p: Preset) -> Polygon:
    cx, cy = p.camera_center()
    w, h, r = camera_cutout_dims(p)
    return rrect_poly(w, h, r, cx, cy)


def _polys(geom) -> list[Polygon]:
    """Polygon parts (area > 0.5 mm2) of any shapely geometry."""
    gs = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    return [g for g in gs if g.geom_type == "Polygon" and g.area > 0.5]


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


def magsafe_ring_poly(p: Preset) -> Polygon:
    """Full MagSafe magnet ring footprint (54.4 mm OD, 45.6 mm ID + bottom alignment tail)."""
    ring = Point(0.0, 0.0).buffer(27.2, quad_segs=48).difference(Point(0.0, 0.0).buffer(22.8, quad_segs=48))
    tail = sbox(-2.4, -38.5, 2.4, -29.0)
    return affinity.translate(ring.union(tail), 0.0, p.style.magsafe_offset_y)


def magsafe_pocket_poly(p: Preset):
    """Internal magnet ring pocket. A real magnet ring cannot be trimmed, so if the ring would
    collide with the camera cutout or run within 2 mm of the plate edge this raises instead of
    silently clipping the pocket."""
    full = magsafe_ring_poly(p)
    edge_keep = plate_outline_poly(p, p.plate_body_offset).buffer(-2.0)
    cam_keepout = camera_cutout_poly(p).buffer(1.5)
    pocket = full.intersection(edge_keep).difference(cam_keepout)
    lost = full.area - pocket.area
    if lost > 0.005 * full.area:
        where = "camera cutout" if full.intersects(cam_keepout) else "backplate edge"
        raise ParamError(
            f"MagSafe ring overlaps the {where} ({100 * lost / full.area:.0f}% of the ring would be cut away). "
            f"Shift it with style.magsafe_offset_y (currently {p.style.magsafe_offset_y:g} mm; "
            f"negative moves it towards the bottom) to match your phone's charging coil.")
    return pocket


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
    w, h, r = camera_cutout_dims(p)
    plate = plate.cut(rrect_prism(w, h, r, -1, p.bp_t + 1).moved(Location((cx, cy, 0))))
    # catch groove for the camera-ring snap bead (open to the inner face)
    g = 2 * (p.style.camera_bead - p.clearances.camera_ring_clearance + 0.05)   # per-side growth beyond cutout
    gz0 = p.bp_t - 0.5 - 0.05
    plate = plate.cut(rrect_prism(w + g + 0.0, h + g, r + g / 2, gz0, p.bp_t + 1).moved(Location((cx, cy, 0))))
    if s.magsafe_ring:
        mp = magsafe_pocket_poly(p)
        mags = [g for g in (mp.geoms if hasattr(mp, "geoms") else [mp])
                if g.geom_type == "Polygon" and g.area > 0.5]
        if mags:
            z0 = p.bp_t - s.magsafe_depth
            tools = [Pos(0, 0, z0) * Solid.extrude(_poly_to_face(g), Vector(0, 0, s.magsafe_depth + 0.5))
                     for g in mags]
            plate = plate.cut(Compound(tools)).clean()
    if not _is_valid(plate):
        raise RuntimeError("backplate invalid")
    if with_pattern:
        return apply_backplate_pattern(plate, p)
    return plate


# ----------------------------------------------------------------------------- patterns
def _hex_polys(region: Polygon, pitch: float, web: float) -> list[Polygon]:
    """Flat-top-agnostic hex grid, clipped (2D) to region. pitch = centre spacing."""
    flat = pitch - web                      # flat-to-flat
    R = flat / math.sqrt(3)                 # circumradius
    minx, miny, maxx, maxy = region.bounds
    dx, dy = pitch, pitch * math.sqrt(3) / 2
    base = Polygon([(R * math.cos(math.radians(60 * k + 30)), R * math.sin(math.radians(60 * k + 30)))
                    for k in range(6)])  # pointy-top hex
    out = []
    row = 0
    y = miny - dy
    while y < maxy + dy:
        x = minx - dx + (dx / 2 if row % 2 else 0)
        while x < maxx + dx:
            hx = affinity.translate(base, x, y)
            if region.intersects(hx):
                clipped = region.intersection(hx)
                if not clipped.is_empty and clipped.area >= 0.35 * base.area:
                    out.extend(list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped])
            x += dx
        y += dy
        row += 1
    return out


def svg_to_polys(svg: str | Path, target_w: float, target_h: float, samples: int = 24) -> list[Polygon]:
    """Parse SVG (path string, file path or markup) -> shapely polygons centred on origin, fitted
    into target box. Even-odd fill for holes; y flipped (SVG y is down)."""
    from svgelements import SVG, Path as SPath, Shape
    import io
    src = svg
    if isinstance(src, Path) or (isinstance(src, str) and len(src) < 260 and Path(src).exists()):
        doc = SVG.parse(str(src))
    else:
        doc = SVG.parse(io.StringIO(src))
    rings = []
    for el in doc.elements():
        if isinstance(el, Shape):
            path = SPath(el)
            path.reify()
            for sub in path.as_subpaths():
                sp = SPath(sub)
                n = max(samples * len(sp), 8)
                pts = [sp.point(t / n) for t in range(n + 1)]
                pts = [(pt.x, -pt.y) for pt in pts if pt is not None]
                if len(pts) >= 4:
                    poly = Polygon(pts).buffer(0)
                    if not poly.is_empty and poly.area > 1e-6:
                        rings.append(poly)
    if not rings:
        raise ValueError("SVG contained no usable shapes")
    # even-odd: XOR all rings
    geom = rings[0]
    for r in rings[1:]:
        geom = geom.symmetric_difference(r)
    minx, miny, maxx, maxy = geom.bounds
    k = min(target_w / (maxx - minx), target_h / (maxy - miny))
    geom = affinity.translate(geom, -(minx + maxx) / 2, -(miny + maxy) / 2)
    geom = affinity.scale(geom, k, k, origin=(0, 0))
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def text_to_polys(text: str, target_w: float, target_h: float, font: str = "Arial",
                  font_size: float = 10.0, bold: bool = False) -> list[Polygon]:
    """build123d native Text() sketch -> sampled wires -> shapely polygons (centred, fitted)."""
    from build123d import FontStyle, Text
    style = FontStyle.BOLD if bold else FontStyle.REGULAR
    txt = Text(text, font_size, font=font, font_style=style)
    polys = []
    for face in txt.faces():
        def ring(wire, n_per_edge=24):
            pts = []
            for e in wire.edges():
                for i in range(n_per_edge):
                    q = e.position_at(i / n_per_edge)
                    pts.append((q.X, q.Y))
            return pts
        outer = ring(face.outer_wire())
        holes = [ring(w) for w in face.inner_wires()]
        poly = Polygon(outer, holes).buffer(0)
        if not poly.is_empty:
            polys.append(poly)
    if not polys:
        raise ValueError(f"Text produced no geometry (font '{font}' missing?)")
    geom = unary_union(polys)
    minx, miny, maxx, maxy = geom.bounds
    k = min(target_w / (maxx - minx), target_h / (maxy - miny))
    geom = affinity.translate(geom, -(minx + maxx) / 2, -(miny + maxy) / 2)
    geom = affinity.scale(geom, k, k, origin=(0, 0))
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def _voronoi_polys(region: Polygon, pitch: float, web: float, seed: int = 42) -> list[Polygon]:
    """Jittered Voronoi cells, inset by web/2 and clipped in 2D to region."""
    rng = np.random.default_rng(int(seed))
    minx, miny, maxx, maxy = region.bounds
    xs = np.arange(minx - pitch, maxx + pitch * 1.5, pitch)
    ys = np.arange(miny - pitch, maxy + pitch * 1.5, pitch)
    pts = []
    for y in ys:
        for x in xs:
            pts.append((float(x + rng.uniform(-0.35, 0.35) * pitch),
                        float(y + rng.uniform(-0.35, 0.35) * pitch)))
    vp = voronoi_polygons(MultiPoint(pts), extend_to=region.envelope.buffer(pitch * 2))
    out = []
    for cell in vp.geoms:
        shrunk = cell.buffer(-web / 2, join_style=2)
        if shrunk.is_empty or not region.intersects(shrunk):
            continue
        clipped = region.intersection(shrunk)
        for g in (clipped.geoms if hasattr(clipped, "geoms") else [clipped]):
            if g.geom_type == "Polygon" and g.area >= 1.5:
                out.append(g)
    return out


def _grid_polys(region: Polygon, pitch: float, web: float, angle: float = 45.0) -> list[Polygon]:
    """Rotated square/diamond lattice clipped in 2D."""
    cell = max(1.0, pitch - web)
    minx, miny, maxx, maxy = region.bounds
    span = math.hypot(maxx - minx, maxy - miny) / 2 + pitch * 2
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    out = []
    min_area = 0.35 * (cell ** 2)
    y = cy - span
    while y <= cy + span:
        x = cx - span
        while x <= cx + span:
            sq = sbox(x - cell / 2, y - cell / 2, x + cell / 2, y + cell / 2)
            if abs(angle) > 1e-3:
                sq = affinity.rotate(sq, angle, origin=(cx, cy))
            if region.intersects(sq):
                clipped = region.intersection(sq)
                for g in (clipped.geoms if hasattr(clipped, "geoms") else [clipped]):
                    if g.geom_type == "Polygon" and g.area >= min_area:
                        out.append(g)
            x += pitch
        y += pitch
    return out


def _wave_polys(region: Polygon, pitch: float, web: float, amplitude: float = 3.5, wavelength: float = 28.0) -> list[Polygon]:
    """Sinusoidal ribbon cutouts buffered and clipped in 2D.
    Bands repeat every `pitch` mm vertically, but the rib between them is measured perpendicular
    to the curve: at the steepest point it shrinks by cos(theta_max), so the slot width is sized
    from that worst case to keep every rib >= `web` (it used to drop to ~0.1 mm)."""
    half_slot = max(0.5, (pitch * wave_cos(amplitude, wavelength) - web) / 2)
    minx, miny, maxx, maxy = region.bounds
    xs = np.linspace(minx - pitch, maxx + pitch, 24)
    out = []
    y0 = miny - amplitude - pitch
    while y0 <= maxy + amplitude + pitch:
        pts = [(float(x), float(y0 + amplitude * math.sin(2 * math.pi * x / max(wavelength, 6.0)))) for x in xs]
        band = LineString(pts).buffer(half_slot, cap_style=2, quad_segs=4)
        if region.intersects(band):
            clipped = region.intersection(band).simplify(0.15, preserve_topology=True)
            for g in (clipped.geoms if hasattr(clipped, "geoms") else [clipped]):
                if g.geom_type == "Polygon" and g.area >= 2.0:
                    out.append(g)
        y0 += pitch
    return out


def _apply_stencil_bridges(polys: list[Polygon], bridge_w: float = 1.4) -> list[Polygon]:
    """Cut narrow vertical bridges across interior rings so through-cut counters stay anchored."""
    out = []
    for g in polys:
        if len(g.interiors) == 0:
            out.append(g)
            continue
        minx, miny, maxx, maxy = g.bounds
        cur = g
        for ir in g.interiors:
            cx, _ = Polygon(ir).centroid.coords[0]
            bar = sbox(cx - bridge_w / 2, miny - 1.0, cx + bridge_w / 2, maxy + 1.0)
            cur = cur.difference(bar)
        for piece in (cur.geoms if hasattr(cur, "geoms") else [cur]):
            if piece.geom_type == "Polygon" and piece.area > 0.5:
                out.append(piece)
    return out


def pattern_polys(p: Preset) -> list[Polygon]:
    pat = p.pattern
    if pat.type == "solid":
        return []
    region = plate_outline_poly(p, p.plate_body_offset).buffer(-pat.margin)
    region = region.difference(camera_cutout_poly(p).buffer(pat.margin))
    if (p.style.magsafe_ring and pat.mode in ("deboss", "inlay")
            and p.bp_t - pat.depth - p.style.magsafe_depth < MIN_FLOOR):
        # Outer-face recess + inner-face magnet pocket would meet in a too-thin (or holed) skin:
        # keep the pattern off the pocket footprint, plus one web of wall around it.
        # (coarse outline: the 48-segment ring arcs otherwise bloat every clipped cell's B-rep)
        keepout = magsafe_pocket_poly(p).buffer(pat.web, quad_segs=6).simplify(0.05)
        region = region.difference(keepout)
    pitch = float(pat.params.get("pitch", PATTERN_DEFAULT_PITCH.get(pat.type, 0.0)))
    if pat.type == "hex":
        return _hex_polys(region, pitch, pat.web)
    if pat.type == "voronoi":
        return _voronoi_polys(region, pitch, pat.web, int(pat.params.get("seed", 42)))
    if pat.type == "grid":
        return _grid_polys(region, pitch, pat.web, float(pat.params.get("angle", 45.0)))
    if pat.type == "waves":
        return _wave_polys(region, pitch, pat.web,
                           float(pat.params.get("amplitude", 3.5)),
                           float(pat.params.get("wavelength", 28.0)))
    if pat.type == "svg":
        minx, miny, maxx, maxy = region.bounds
        size = float(pat.params.get("size", 0.8))
        polys = svg_to_polys(pat.params["svg"], (maxx - minx) * size, (maxy - miny) * size)
        polys = [affinity.scale(g, -1, 1, origin=(0, 0)) for g in polys]  # read correctly from the OUTER face
        ox, oy = pat.params.get("offset", (0.0, 0.0))
        polys = [affinity.translate(g, ox, oy) for g in polys]
        clipped = unary_union(polys).intersection(region)
        res = list(clipped.geoms) if hasattr(clipped, "geoms") else ([] if clipped.is_empty else [clipped])
        if pat.mode == "through" and pat.stencil_bridges:
            res = _apply_stencil_bridges(res)
        return res
    if pat.type == "text":
        minx, miny, maxx, maxy = region.bounds
        size = float(pat.params.get("size", 0.7))
        polys = text_to_polys(pat.params.get("text", "TEXT"), (maxx - minx) * size, (maxy - miny) * size,
                              pat.params.get("font", "Arial"), float(pat.params.get("font_size", 10.0)),
                              bool(pat.params.get("bold", True)))
        rot = float(pat.params.get("rotation", 0.0))
        polys = [affinity.rotate(g, rot, origin=(0, 0)) for g in polys]
        polys = [affinity.scale(g, -1, 1, origin=(0, 0)) for g in polys]  # read correctly from the OUTER face
        ox, oy = pat.params.get("offset", (0.0, 0.0))
        polys = [affinity.translate(g, ox, oy) for g in polys]
        clipped = unary_union(polys).intersection(region)
        res = list(clipped.geoms) if hasattr(clipped, "geoms") else ([] if clipped.is_empty else [clipped])
        if pat.mode == "through" and pat.stencil_bridges:
            res = _apply_stencil_bridges(res)
        return res
    raise ValueError(pat.type)


def _poly_to_face(poly: Polygon) -> Face:
    def wire(coords):
        pts = [Vector(x, y, 0) for x, y in list(coords)[:-1]]
        return Wire.make_polygon(pts, close=True)
    return Face(wire(poly.exterior.coords), [wire(i.coords) for i in poly.interiors])


_ISLAND_HINT = {
    "text": "Enable stencil bridges, use a bolder font/larger size, or switch to deboss or inlay.",
    "svg": "Enable stencil bridges, remove enclosed shapes from the SVG, or switch to deboss or inlay.",
}


def through_cut_material(p: Preset, polys: list[Polygon]):
    """2D backplate material left after a through-cut (plate outline - camera cutout - pattern)."""
    base = plate_outline_poly(p, p.plate_body_offset).difference(camera_cutout_poly(p))
    return base.difference(unary_union(polys)) if polys else base


def through_cut_connectivity(p: Preset, polys: list[Polygon] | None = None) -> dict:
    """Connectivity of a through-cut backplate, computed in 2D (cheap, exact for prismatic cuts).

    Openings are holes in ONE material region; detached solids are extra material regions that
    would fall out of the print. Returns {"islands": [(area, (x, y)), ...] (detached pieces,
    largest first), "thin_necks": n regions joined only by ligaments < MIN_PATTERN_WEB}."""
    from params import MIN_PATTERN_WEB
    if polys is None:
        polys = [g for g in pattern_polys(p) if g.area > 0.5 and g.geom_type == "Polygon"]
    regions = sorted(_polys(through_cut_material(p, polys)), key=lambda g: -g.area)
    islands = [(round(g.area, 1), tuple(round(v, 1) for v in g.representative_point().coords[0]))
               for g in regions[1:]]
    thin = 0
    if regions:
        eroded = [g for g in _polys(regions[0].buffer(-MIN_PATTERN_WEB / 2)) if g.area > 2.0]
        thin = max(0, len(eroded) - 1)
    return {"islands": islands, "thin_necks": thin}


def _check_through_cut(p: Preset, polys: list[Polygon]) -> None:
    conn = through_cut_connectivity(p, polys)
    isl = conn["islands"]
    if not isl:
        if conn["thin_necks"]:
            log.warning("through-cut leaves regions joined by ligaments thinner than one extrusion width")
        return
    area, (x, y) = isl[0]
    hint = _ISLAND_HINT.get(p.pattern.type,
                            "Increase the material web width, increase the pattern margin, or switch to deboss.")
    if p.pattern.type in _ISLAND_HINT and p.pattern.stencil_bridges:
        hint = hint.replace("Enable stencil bridges, ", "")
    raise ParamError(
        f"Your through-cut {p.pattern.type} pattern creates {len(isl)} disconnected region"
        f"{'s' if len(isl) != 1 else ''} that would fall out of the backplate (largest {area:g} mm2 "
        f"at x={x:g}, y={y:g} mm from the plate centre, front view). {hint}")


def apply_backplate_pattern(plate: Solid, p: Preset):
    """2D boolean first (shapely), then ONE extrusion batch + ONE cut. Returns (plate, inlay).
    Through-cuts that would detach material are rejected (ParamError) before any 3D work."""
    pat = p.pattern
    polys = [g for g in pattern_polys(p) if g.area > 0.5 and g.geom_type == "Polygon"]
    if not polys:
        return plate, None
    if pat.mode == "through":
        _check_through_cut(p, polys)
    if pat.mode == "through":
        z0, h = -1.0, p.bp_t + 2.0
    else:
        z0, h = -1.0, pat.depth + 1.0           # cutter starts below outer face, depth = pat.depth
    tools = []
    for g in polys:
        tools.append(Pos(0, 0, z0) * Solid.extrude(_poly_to_face(g), Vector(0, 0, h)))
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
        shrunk = []
        for g in polys:
            sg = g.buffer(-p.sc / 2)
            if not sg.is_empty:
                shrunk.extend(list(sg.geoms) if hasattr(sg, "geoms") else [sg])
        inl = [Solid.extrude(_poly_to_face(sg), Vector(0, 0, pat.depth))
               for sg in shrunk if sg.geom_type == "Polygon" and sg.area > 0.1]
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
    shape = laser_polys(p)
    geoms = list(shape.geoms) if hasattr(shape, "geoms") else [shape]
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
    Path(path).write_text(svg, encoding="utf-8")
    return Path(path)


# ----------------------------------------------------------------------------- camera ring
def generate_camera_ring(p: Preset) -> Solid:
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


def orient_for_print(shape, center_xy: bool = True, rot=None, ref=None):
    """Orient a part for FDM and ground it at Z=0, centred in XY.
    `rot` = explicit (rx, ry, rz) chosen per part for support-free printing (frame: lip down,
    plate: outer face down, ring: bezel down, button: cap down). Without it, falls back to the
    axis-aligned orientation with the largest flat bed contact (tie-break: lowest height)."""
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
    bb = (Rot(*(rot if rot is not None else (0, 0, 0))) * ref).bounding_box() if ref is not None else out.bounding_box()
    cx = (bb.min.X + bb.max.X) / 2 if center_xy else 0
    cy = (bb.min.Y + bb.max.Y) / 2 if center_xy else 0
    return Pos(-cx, -cy, -bb.min.Z) * out


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
    ring = timed("camera_ring", lambda: generate_camera_ring(p))
    btns = timed("buttons", lambda: generate_buttons(p))
    oriented = {
        "Frame_TPU": orient_for_print(frame, rot=(0, 0, 0)),       # BACK-DOWN: rear face on bed, lip prints last
        "Backplate_PLA": orient_for_print(plate, rot=(0, 0, 0)),   # outer face on bed
        "CameraRing": orient_for_print(ring, rot=(0, 0, 0)),       # bezel on bed
    }
    if btns:
        oriented["Buttons"] = Compound(layout_row([button_print_shape(p, b) for b in p.buttons]), label="Buttons")
    if inlay is not None:
        oriented["Backplate_Inlay"] = orient_for_print(inlay, rot=(0, 0, 0), ref=plate)  # same transform as plate
    design = {"frame": frame, "plate": plate, "inlay": inlay, "ring": ring, "buttons": btns}
    return {"design": design, "oriented": oriented, "timings": timings}


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

    asm_children = [_label(d["frame"], "Frame"), _label(d["plate"], "Backplate"), _label(d["ring"], "CameraRing")]
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
    notes.append("Unibody: the camera surround is flush with the back (a raised bezel would lift the "
                 "case off the bed when printing back-down); use the modular camera ring for a raised guard.")
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
    cx, cy = q.camera_center()
    cuts += [Pos(cx, cy, 0) * t for t in camera_aperture_cutters(q, 0.0, q.bp_t)]
    body = _frame_outer(q)
    for cutter in cuts:
        body = body.cut(cutter)
    for b in q.buttons:
        body = body.fuse(place_on_edge(_button_cover_local(q, b), q, b.side, button_along(q, b), button_zc(q)))
    if q.style.magsafe_ring:                 # magnets drop into the floor from the phone side
        for g in _polys(magsafe_pocket_poly(q)):
            z0 = q.bp_t - q.style.magsafe_depth
            body = body.cut(Pos(0, 0, z0) * Solid.extrude(_poly_to_face(g), Vector(0, 0, q.style.magsafe_depth + 0.5)))
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
    Returns dict(x0,x1,y0,y1,sx,button)."""
    cx, cy = p.camera_center()
    cw, ch, _ = camera_cutout_dims(p)
    bez = p.style.camera_bezel_width
    sx = 1 if cx >= 0 else -1
    side = "right" if sx > 0 else "left"
    cands = [b for b in p.buttons if b.side == side]
    btn = min(cands, key=lambda b: abs(button_along(p, b) - cy)) if cands else None
    outer = p.outer_offset
    x_edge, y_edge = sx * (p.W / 2 + outer + 1), p.L / 2 + outer + 1
    x_in = cx - sx * (cw / 2 + bez + margin)
    y_lo = cy - (ch / 2 + bez + margin)
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
    ring = generate_camera_ring(q)
    oriented = {
        "Frame_TPU_coupon": orient_for_print(frame, rot=(0, 0, 0)),
        "Backplate_PLA_coupon": orient_for_print(plate, rot=(0, 0, 0)),
        "CameraRing": orient_for_print(ring, rot=(0, 0, 0)),
    }
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
