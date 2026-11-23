"""2D backplate geometry and the pattern library (Shapely; text glyphs via build123d/OCCT).

Everything here is planar and cheap, so the UI can preview a design in milliseconds while the
B-rep is rebuilt; cad_engine turns the result into solids. Coordinates are DESIGN coordinates
(see params.py): origin at the centre of the phone's back, +X = the phone's right seen from the
FRONT, +Y = towards the top.

Public API:
    plate_outline_poly(p, offset), camera_cutout_poly(p), magsafe_ring_poly(p), magsafe_pocket_poly(p)
    pattern_region(p)                    area the pattern may occupy
    pattern_cells(p) -> [Cell]           final cut-outs (cached); pattern_polys(p) -> [Polygon]
    through_cut_connectivity(p), check_through_cut(p, polys)
    PATTERN_SPECS, public_specs()        generator metadata the UI renders its controls from
    pattern_preview(p), pattern_gallery(p)   back-view SVG path data for the UI

Pattern finishing (lattices: hex, dots, triangles, grid, voronoi):
    edge = clip   cells are cut at the border of the patterned area (the original behaviour;
                  saved designs build exactly as before)
           whole  only complete cells, leaving a clean solid border
           fade   cells shrink towards the border over `fade_width` mm (smoothstep, >= 25 %)
    corner_radius rounds every convex cut-out corner (lattices and stripes): a morphological
                  opening, so a cut-out can only shrink and connectivity can only improve.
Stripes (waves, chevron) are always clipped; text and SVG artwork are placed as drawn.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import shapely
from shapely import affinity, voronoi_polygons
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon, box as sbox
from shapely.ops import unary_union

from params import (MIN_FLOOR, MIN_PATTERN_WEB, PATTERN_DEFAULT_PITCH, STRIPE_SHAPES, ParamError,
                    Preset, stripe_cos)

log = logging.getLogger("casecraft")
LATTICE_TYPES = ("hex", "dots", "triangles", "grid", "voronoi")
EMBLEM_TYPES = ("text", "svg")
FADE_MIN_SCALE = 0.25          # smallest cell (fraction of full size) kept by edge == "fade"
FADE_MIN_AREA = 2.0            # mm2 (~1.6 mm hole): smaller faded cells close up on an FDM print
ROUND_CHORD_TOL = 0.08         # mm: max deviation of the polygonal corner arcs (below FDM resolution)
MIN_CUT_AREA = 0.5             # mm2: smaller cut-outs are dropped (they would not print)
THIN_MIN_AREA = 0.3            # mm2: thin-ligament residue shown in the preview


# ----------------------------------------------------------------------------- plate geometry
def rrect_poly(w: float, l: float, r: float, cx=0.0, cy=0.0) -> Polygon:
    r = max(0.0, min(r, 0.499 * min(w, l)))
    if r < 1e-3:
        return sbox(cx - w / 2, cy - l / 2, cx + w / 2, cy + l / 2)
    core = sbox(cx - w / 2 + r, cy - l / 2 + r, cx + w / 2 - r, cy + l / 2 - r)
    return core.buffer(r, quad_segs=24)


def plate_outline_poly(p: Preset, offset: float) -> Polygon:
    return rrect_poly(p.W + 2 * offset, p.L + 2 * offset, p.body.corner_radius + offset)


def camera_cutout_dims(p: Preset):
    c, s = p.camera, p.style
    m = s.camera_cutout_margin
    return c.width + 2 * m, c.height + 2 * m, c.radius + m


def camera_cutout_poly(p: Preset) -> Polygon:
    cx, cy = p.camera_center()
    w, h, r = camera_cutout_dims(p)
    return rrect_poly(w, h, r, cx, cy)


def _polys(geom) -> list[Polygon]:
    """Polygon parts (area > 0.5 mm2) of any shapely geometry."""
    gs = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    return [g for g in gs if g.geom_type == "Polygon" and g.area > 0.5]


def _parts(geom) -> list:
    """Every part of a (possibly multi-part / collection) geometry, empty geometry -> []."""
    if geom.is_empty:
        return []
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]


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


def pattern_region(p: Preset):
    """Where the pattern may cut: the plate body inset by the margin, minus the camera cutout
    (plus margin) and, for a deboss/inlay over a MagSafe pocket, the pocket footprint."""
    pat = p.pattern
    region = plate_outline_poly(p, p.plate_body_offset).buffer(-pat.margin)
    region = region.difference(camera_cutout_poly(p).buffer(pat.margin))
    if (p.style.magsafe_ring and pat.mode in ("deboss", "inlay")
            and p.bp_t - pat.depth - p.style.magsafe_depth < MIN_FLOOR):
        # Outer-face recess + inner-face magnet pocket would meet in a too-thin (or holed) skin:
        # keep the pattern off the pocket footprint, plus one web of wall around it.
        # (coarse outline: the 48-segment ring arcs otherwise bloat every clipped cell's B-rep)
        keepout = magsafe_pocket_poly(p).buffer(pat.web, quad_segs=6).simplify(0.05)
        region = region.difference(keepout)
    return region


# ----------------------------------------------------------------------------- cells
@dataclass(frozen=True)
class Cell:
    """One cut-out. `poly` drives every 2D check, the preview and the laser SVG; `circle`
    (cx, cy, r) marks an exact circle so the B-rep tool can be a true cylinder (one face
    instead of dozens, ~40x faster to cut)."""
    poly: Polygon
    circle: tuple[float, float, float] | None = None


# raw generators: unclipped cells covering the region's bounds -> ([(poly, circle|None)], keep rule)
# keep rules reproduce the original clip behaviour of each generator exactly:
#   ("cell", A)  keep every piece of a clipped cell when >= 35 % of the nominal cell area A survives
#   ("piece", A) keep each clipped piece of >= 35 % of A          ("abs", a) keep pieces >= a mm2
def _stagger_points(region, dx: float, dy: float, centered: bool):
    """Centres of a staggered (hexagonal) lattice covering the region bounds. `centered` puts a
    lattice point on the plate centre, so the layout is mirror-symmetric about the phone's
    vertical axis; otherwise it is anchored at the region's lower-left corner (the original
    clip layout, kept so saved designs build identically)."""
    minx, miny, maxx, maxy = region.bounds
    pts = []
    if centered:
        j0, j1 = math.floor((miny - dy) / dy), math.ceil((maxy + dy) / dy)
        for j in range(j0, j1 + 1):
            shift = dx / 2 if j % 2 else 0.0
            i0, i1 = math.floor((minx - dx - shift) / dx), math.ceil((maxx + dx - shift) / dx)
            pts.extend((i * dx + shift, j * dy) for i in range(i0, i1 + 1))
        return pts
    row = 0
    y = miny - dy
    while y < maxy + dy:
        x = minx - dx + (dx / 2 if row % 2 else 0)
        while x < maxx + dx:
            pts.append((x, y))
            x += dx
        y += dy
        row += 1
    return pts


def _hex_raw(region, pitch: float, web: float, centered: bool = False):
    """Pointy-top hexagons on a staggered grid; pitch = centre spacing, flats = pitch - web."""
    flat = pitch - web
    R = flat / math.sqrt(3)
    base = Polygon([(R * math.cos(math.radians(60 * k + 30)), R * math.sin(math.radians(60 * k + 30)))
                    for k in range(6)])
    out = []
    for x, y in _stagger_points(region, pitch, pitch * math.sqrt(3) / 2, centered):
        hx = affinity.translate(base, x, y)
        if region.intersects(hx):
            out.append((hx, None))
    return out, ("cell", base.area)


def _dots_raw(region, pitch: float, web: float):
    """Round holes on a hexagonal packing; diameter = pitch - web. Exact circles for the B-rep."""
    r = (pitch - web) / 2
    # 32-gon for the 2D checks/drawing (<= 0.01 mm off for these sizes); whole dots are cut as
    # true circles, only dots cut by the border keep this polygon in the B-rep
    template = Point(0.0, 0.0).buffer(r, quad_segs=8)
    out = []
    for x, y in _stagger_points(region, pitch, pitch * math.sqrt(3) / 2, centered=True):
        c = affinity.translate(template, x, y)
        if region.intersects(c):
            out.append((c, (float(x), float(y), r)))
    return out, ("cell", template.area)


def _triangles_raw(region, pitch: float, web: float, angle: float = 0.0):
    """Equilateral triangle tiling (side = pitch), each tile inset by web/2, rotated by angle
    about the plate centre. An upward tile is centred on the phone's vertical axis, so the
    layout is mirror-symmetric."""
    a, h = pitch, pitch * math.sqrt(3) / 2
    minx, miny, maxx, maxy = region.bounds
    cx, cy = -a / 2, 0.0                   # lower-left corner of the tile centred on x = 0
    span = max(abs(minx), abs(maxx), abs(miny), abs(maxy)) * math.sqrt(2) + 2 * a
    up = Polygon([(0, 0), (a, 0), (a / 2, h)]).buffer(-web / 2, join_style="mitre")
    down = Polygon([(a / 2, h), (3 * a / 2, h), (a, 0)]).buffer(-web / 2, join_style="mitre")
    out = []
    if up.is_empty:
        return out, ("cell", 1.0)
    nrows = int(math.ceil(span / h))
    ncols = int(math.ceil(span / a)) + 1
    for j in range(-nrows, nrows + 1):
        y = cy + j * h
        x0 = cx - ncols * a + (a / 2 if j % 2 else 0)
        for i in range(2 * ncols + 1):
            x = x0 + i * a
            for tri in (up, down):
                t = affinity.translate(tri, x, y)
                if abs(angle) > 1e-3:
                    t = affinity.rotate(t, angle, origin=(0.0, 0.0))
                if region.intersects(t):
                    out.append((t, None))
    return out, ("cell", up.area)


def _grid_raw(region, pitch: float, web: float, angle: float = 45.0, centered: bool = False):
    """Rotated square/diamond lattice, about the region's bounding-box centre (the original clip
    layout) or, `centered`, about the plate centre so the layout is mirror-symmetric."""
    cell = max(1.0, pitch - web)
    minx, miny, maxx, maxy = region.bounds
    if centered:
        cx, cy = 0.0, 0.0
        span = max(abs(minx), abs(maxx), abs(miny), abs(maxy)) * math.sqrt(2) + pitch * 2
        span = math.ceil(span / pitch) * pitch          # keep a lattice point on the centre
    else:
        span = math.hypot(maxx - minx, maxy - miny) / 2 + pitch * 2
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    out = []
    y = cy - span
    while y <= cy + span:
        x = cx - span
        while x <= cx + span:
            sq = sbox(x - cell / 2, y - cell / 2, x + cell / 2, y + cell / 2)
            if abs(angle) > 1e-3:
                sq = affinity.rotate(sq, angle, origin=(cx, cy))
            if region.intersects(sq):
                out.append((sq, None))
            x += pitch
        y += pitch
    return out, ("piece", cell ** 2)


def _voronoi_raw(region, pitch: float, web: float, seed: int = 42, relax: int = 0):
    """Jittered Voronoi cells inset by web/2. `relax` Lloyd iterations even out the cell sizes
    (0 = the original jittered-grid look)."""
    rng = np.random.default_rng(int(seed))
    minx, miny, maxx, maxy = region.bounds
    xs = np.arange(minx - pitch, maxx + pitch * 1.5, pitch)
    ys = np.arange(miny - pitch, maxy + pitch * 1.5, pitch)
    pts = []
    for y in ys:
        for x in xs:
            pts.append((float(x + rng.uniform(-0.35, 0.35) * pitch),
                        float(y + rng.uniform(-0.35, 0.35) * pitch)))
    extent = region.envelope.buffer(pitch * 2)
    for _ in range(int(relax)):
        frame = sbox(*extent.bounds)
        cells = voronoi_polygons(MultiPoint(pts), extend_to=extent)
        pts = [tuple(c.intersection(frame).centroid.coords[0]) for c in cells.geoms
               if not c.intersection(frame).is_empty]
    vp = voronoi_polygons(MultiPoint(pts), extend_to=extent)
    out = []
    for cell in vp.geoms:
        shrunk = cell.buffer(-web / 2, join_style=2)
        if shrunk.is_empty or not region.intersects(shrunk):
            continue
        out.append((shrunk, None))
    return out, ("abs", 1.5)


def _stripe_raw(region, pitch: float, web: float, amplitude: float, wavelength: float, shape: str):
    """Wavy (sine) or zig-zag (chevron) slots repeating every `pitch` mm vertically. The rib
    between bands is measured perpendicular to the band at its steepest point, so the slot is
    sized from that worst case to keep every rib >= `web`. Sine bands are sampled densely and
    simplified to 0.08 mm by the caller (the old 24-sample polyline visibly flattened the crests)."""
    half_slot = max(0.5, (pitch * stripe_cos(amplitude, wavelength, shape) - web) / 2)
    wl = max(wavelength, 6.0)
    minx, miny, maxx, maxy = region.bounds
    x0, x1 = minx - pitch, maxx + pitch
    if shape == "chevron":
        k0, k1 = math.floor((x0 - wl / 4) / (wl / 2)), math.ceil((x1 - wl / 4) / (wl / 2))
        xs = [wl / 4 + k * wl / 2 for k in range(k0, k1 + 1)]
        offsets = [amplitude if k % 2 == 0 else -amplitude for k in range(k0, k1 + 1)]
        join = "mitre"
    else:
        n = max(24, int(math.ceil((x1 - x0) / (wl / 48))))
        xs = np.linspace(x0, x1, n)
        offsets = [amplitude * math.sin(2 * math.pi * x / wl) for x in xs]
        join = "round"
    out = []
    y0 = miny - amplitude - pitch
    while y0 <= maxy + amplitude + pitch:
        line = LineString([(float(x), float(y0 + o)) for x, o in zip(xs, offsets)])
        band = line.buffer(half_slot, cap_style="flat", join_style=join, mitre_limit=10.0, quad_segs=4)
        if region.intersects(band):
            out.append((band, None))
        y0 += pitch
    return out, ("abs", 2.0)


def _lattice_raw(t: str, region, pitch: float, web: float, pr: dict, centered: bool):
    if t == "hex":
        return _hex_raw(region, pitch, web, centered)
    if t == "dots":
        return _dots_raw(region, pitch, web)
    if t == "triangles":
        return _triangles_raw(region, pitch, web, float(pr.get("angle", 0.0)))
    if t == "grid":
        return _grid_raw(region, pitch, web, float(pr.get("angle", 45.0)), centered)
    if t == "voronoi":
        return _voronoi_raw(region, pitch, web, int(pr.get("seed", 42)), int(pr.get("relax", 0)))
    raise ValueError(t)


# ----------------------------------------------------------------------------- finishing
def _clip(region, raw, rule, simplify: float = 0.0):
    kind, ref = rule
    out = []
    for poly, circ in raw:
        if circ is not None and region.contains(poly):
            out.append((poly, circ))           # whole circle: keep it exact
            continue
        clipped = region.intersection(poly)
        if simplify:
            clipped = clipped.simplify(simplify, preserve_topology=True)
        parts = _parts(clipped)
        if kind == "cell":
            if parts and clipped.area >= 0.35 * ref:
                out.extend((g, None) for g in parts)
        elif kind == "piece":
            out.extend((g, None) for g in parts if g.geom_type == "Polygon" and g.area >= 0.35 * ref)
        else:
            out.extend((g, None) for g in parts if g.geom_type == "Polygon" and g.area >= ref)
    return out


def _whole(region, raw):
    return [(poly, circ) for poly, circ in raw if region.contains(poly)]


def _fade(region, raw, fade_width: float):
    """Scale each cell about its centre by a smoothstep of its distance to the border."""
    boundary = region.boundary
    out = []
    for poly, circ in raw:
        ctr = Point(circ[0], circ[1]) if circ is not None else poly.centroid
        if not region.contains(ctr):
            continue
        t = min(1.0, boundary.distance(ctr) / fade_width)
        s = FADE_MIN_SCALE + (1 - FADE_MIN_SCALE) * t * t * (3 - 2 * t)
        if s < 0.999:
            poly = affinity.scale(poly, s, s, origin=ctr)
            circ = (circ[0], circ[1], circ[2] * s) if circ is not None else None
        if poly.area >= FADE_MIN_AREA and region.contains(poly):
            out.append((poly, circ))
    return out


def _quad_segs(r: float) -> int:
    """Segments per quarter circle so the polygonal arc stays within ROUND_CHORD_TOL. Polygon arcs
    cost about 2x boolean time, true arcs (fillet_2d) cost more to build: measured, see report."""
    if r <= ROUND_CHORD_TOL:
        return 1
    theta = 2 * math.acos(1 - ROUND_CHORD_TOL / r)
    return max(1, min(6, math.ceil((math.pi / 2) / theta)))


def _round(cells, r: float, simplify: float = 0.0):
    """Round the convex corners of each cut-out by r (morphological opening: never grows a cut)."""
    if r <= 0:
        return cells
    q = _quad_segs(r)
    out = []
    for poly, circ in cells:
        if circ is not None:
            out.append((poly, circ))
            continue
        opened = poly.buffer(-r, quad_segs=q, join_style="round").buffer(r, quad_segs=q, join_style="round")
        if poly.convex_hull.area > poly.area * (1 + 1e-9):
            # the polygonal erosion arc at a concave corner lets the dilation overshoot the
            # corner by up to the chord tolerance; trim back so the web is never reduced
            opened = opened.intersection(poly)
        for g in _parts(opened):
            if g.geom_type == "Polygon":
                out.append((g.simplify(simplify, preserve_topology=True) if simplify else g, None))
    return out


# ----------------------------------------------------------------------------- text / SVG artwork
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


_TEXT_LOCK = threading.Lock()   # OCCT's font manager is process-global: one glyph build at a time


def text_to_polys(text: str, target_w: float, target_h: float, font: str = "Arial",
                  font_size: float = 10.0, bold: bool = False) -> list[Polygon]:
    """build123d native Text() sketch -> sampled wires -> shapely polygons (centred, fitted).
    Cached: the preview, the 2D checks and the laser SVG all ask for the same glyphs."""
    return list(_text_polys(str(text), float(target_w), float(target_h), str(font), float(font_size), bool(bold)))


@lru_cache(maxsize=64)
def _text_polys(text, target_w, target_h, font, font_size, bold) -> tuple[Polygon, ...]:
    from build123d import FontStyle, Text
    style = FontStyle.BOLD if bold else FontStyle.REGULAR
    with _TEXT_LOCK:
        txt = Text(text, font_size, font=font, font_style=style)
        faces = list(txt.faces())
        polys = []
        for face in faces:
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
    return tuple(geom.geoms) if isinstance(geom, MultiPolygon) else (geom,)


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


def _emblem_polys(p: Preset, region) -> list:
    """Text or SVG artwork: fitted into `size` x the patterned area, rotated (CCW as seen from
    the back), mirrored so it reads correctly from the OUTER face, then offset (design coords)."""
    pat = p.pattern
    pr = pat.params
    minx, miny, maxx, maxy = region.bounds
    try:
        if pat.type == "svg":
            if not pr.get("svg"):
                raise ParamError("Choose an SVG emblem or upload an SVG drawing")
            size = float(pr.get("size", 0.8))
            polys = svg_to_polys(pr["svg"], (maxx - minx) * size, (maxy - miny) * size)
        else:
            text = str(pr.get("text", "TEXT"))
            if not text.strip():
                return []                      # nothing to cut yet (the user is still typing)
            size = float(pr.get("size", 0.7))
            polys = text_to_polys(text, (maxx - minx) * size, (maxy - miny) * size,
                                  pr.get("font", "Arial"), float(pr.get("font_size", 10.0)),
                                  bool(pr.get("bold", True)))
    except ParamError:
        raise
    except Exception as exc:  # noqa: BLE001 -- unreadable SVG / glyph failure: a design error, not a crash
        what = "SVG artwork" if pat.type == "svg" else "text"
        raise ParamError(f"Could not build the {what}: {exc}") from exc
    rot = float(pr.get("rotation", 0.0))
    if pat.type == "text" or abs(rot) > 1e-9:
        polys = [affinity.rotate(g, rot, origin=(0, 0)) for g in polys]
    polys = [affinity.scale(g, -1, 1, origin=(0, 0)) for g in polys]  # read correctly from the OUTER face
    ox, oy = pr.get("offset", (0.0, 0.0))
    polys = [affinity.translate(g, ox, oy) for g in polys]
    clipped = unary_union(polys).intersection(region)
    res = list(clipped.geoms) if hasattr(clipped, "geoms") else ([] if clipped.is_empty else [clipped])
    if pat.mode == "through" and pat.stencil_bridges:
        res = _apply_stencil_bridges(res)
    return res


# ----------------------------------------------------------------------------- pattern cells
_CACHE: "OrderedDict[str, tuple[Cell, ...]]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 48


def _design_key(p: Preset) -> str:
    blob = json.dumps(dataclasses.asdict(p), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def pattern_cells(p: Preset) -> list[Cell]:
    """Final cut-outs of the backplate pattern (polygons > 0.5 mm2), cached per design."""
    key = _design_key(p)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return list(hit)
    cells = tuple(_compute_cells(p))
    with _CACHE_LOCK:
        _CACHE[key] = cells
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return list(cells)


def pattern_polys(p: Preset) -> list[Polygon]:
    return [c.poly for c in pattern_cells(p)]


def _compute_cells(p: Preset) -> list[Cell]:
    pat = p.pattern
    if pat.type == "solid":
        return []
    region = pattern_region(p)
    if region.is_empty:
        return []
    shapely.prepare(region)
    pr = pat.params
    if pat.type in EMBLEM_TYPES:
        cells = [(g, None) for g in _emblem_polys(p, region)]
    elif pat.type in STRIPE_SHAPES:
        pitch = float(pr.get("pitch", PATTERN_DEFAULT_PITCH[pat.type]))
        raw, rule = _stripe_raw(region, pitch, pat.web, float(pr.get("amplitude", 3.5)),
                                float(pr.get("wavelength", 28.0)), STRIPE_SHAPES[pat.type])
        # sine bands: 0.08 mm drawing tolerance (invisible in print; every vertex is a B-rep face)
        cells = _clip(region, raw, rule, simplify=0.08 if STRIPE_SHAPES[pat.type] == "sine" else 0.05)
        cells = _round(cells, pat.corner_radius, simplify=0.02)
    elif pat.type in LATTICE_TYPES:
        pitch = float(pr.get("pitch", PATTERN_DEFAULT_PITCH[pat.type]))
        # the new border modes centre the lattice on the plate; clip keeps the original layout
        raw, rule = _lattice_raw(pat.type, region, pitch, pat.web, pr, centered=pat.edge != "clip")
        if pat.edge == "whole":
            cells = _whole(region, raw)
        elif pat.edge == "fade":
            cells = _fade(region, raw, pat.fade_width)
        else:
            cells = _clip(region, raw, rule)
        cells = _round(cells, pat.corner_radius)
    else:
        raise ValueError(pat.type)
    return [Cell(g, circ) for g, circ in cells if g.geom_type == "Polygon" and g.area > MIN_CUT_AREA]


# ----------------------------------------------------------------------------- through-cut checks
_ISLAND_HINT = {
    "text": "Enable stencil bridges, use a bolder font/larger size, or switch to deboss or inlay.",
    "svg": "Enable stencil bridges, remove enclosed shapes from the SVG, or switch to deboss or inlay.",
}


def through_cut_material(p: Preset, polys: list[Polygon]):
    """2D backplate material left after a through-cut (plate outline - camera cutout - pattern)."""
    base = plate_outline_poly(p, p.plate_body_offset).difference(camera_cutout_poly(p))
    return base.difference(unary_union(polys)) if polys else base


def _material_regions(p: Preset, polys: list[Polygon]) -> list[Polygon]:
    """Material regions after a through-cut, largest first (the rest would fall out)."""
    return sorted(_polys(through_cut_material(p, polys)), key=lambda g: -g.area)


def through_cut_connectivity(p: Preset, polys: list[Polygon] | None = None) -> dict:
    """Connectivity of a through-cut backplate, computed in 2D (cheap, exact for prismatic cuts).

    Openings are holes in ONE material region; detached solids are extra material regions that
    would fall out of the print. Returns {"islands": [(area, (x, y)), ...] (detached pieces,
    largest first), "thin_necks": n regions joined only by ligaments < MIN_PATTERN_WEB}."""
    if polys is None:
        polys = pattern_polys(p)
    regions = _material_regions(p, polys)
    islands = [(round(g.area, 1), tuple(round(v, 1) for v in g.representative_point().coords[0]))
               for g in regions[1:]]
    thin = 0
    if regions:
        eroded = [g for g in _polys(regions[0].buffer(-MIN_PATTERN_WEB / 2)) if g.area > 2.0]
        thin = max(0, len(eroded) - 1)
    return {"islands": islands, "thin_necks": thin}


def check_through_cut(p: Preset, polys: list[Polygon]) -> None:
    """Raise ParamError (with the count, size, location and a fix) if a through-cut would
    detach material from the backplate."""
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


def thin_ligaments(material, width: float = MIN_PATTERN_WEB) -> list[Polygon]:
    """Material narrower than `width` (one extrusion): what an opening by width/2 removes."""
    if material.is_empty:
        return []
    opened = material.buffer(-width / 2).buffer(width / 2)
    return [g for g in _parts(material.difference(opened))
            if g.geom_type == "Polygon" and g.area >= THIN_MIN_AREA]


# ----------------------------------------------------------------------------- specs (UI metadata)
STAR_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M50 5 L61 38 L95 38 '
            'L67 58 L78 92 L50 71 L22 92 L33 58 L5 38 L39 38 Z"/><circle cx="50" cy="50" r="8"/></svg>')
FONTS = ("Arial", "Arial Black", "Bahnschrift", "Impact", "Segoe UI", "Georgia", "Trebuchet MS",
         "Verdana", "Consolas", "Courier New")


def _slider(key, label, lo, hi, step, unit="mm", hint=""):
    return {"key": key, "label": label, "kind": "slider", "min": lo, "max": hi, "step": step,
            "unit": unit, "hint": hint}


_PITCH_HINT = "Centre-to-centre spacing; smaller = finer"
_STRIPE = [
    _slider("pitch", "Band spacing", 4.5, 14.0, 0.5, hint="Distance between bands"),
    _slider("amplitude", "Amplitude", 0.0, 8.0, 0.5, hint="Height of each wave"),
]
_PLACEMENT = [
    _slider("size", "Size", 0.25, 0.9, 0.05, unit="×", hint="Fraction of the patterned area"),
    {"key": "offset", "label": "Position", "kind": "xy", "min": -30.0, "max": 30.0, "step": 0.5, "unit": "mm",
     "hint": "Back view: +X right, +Y up", "back_view_x": True},
]
_ALL_EDGES = ["clip", "whole", "fade"]

# Ordered: solid, lattices, stripes, artwork. Every slider extreme (with the other values at
# their defaults and the default web/margin) is a valid design: test_patterns checks it.
PATTERN_SPECS: dict[str, dict] = {
    "solid": {"label": "Solid", "description": "Clean, uninterrupted backplate",
              "family": "solid", "defaults": {}, "controls": [], "edges": [], "rounding": False},
    "hex": {"label": "Hexagon", "description": "Honeycomb mesh: light, stiff and airy",
            "family": "lattice", "defaults": {"pitch": 9.0},
            "controls": [_slider("pitch", "Cell spacing", 5.5, 16.0, 0.5, hint=_PITCH_HINT)],
            "edges": _ALL_EDGES, "rounding": True},
    "dots": {"label": "Dots", "description": "Round perforations, exact circles",
             "family": "lattice", "defaults": {"pitch": 7.0},
             "controls": [_slider("pitch", "Dot spacing", 4.0, 14.0, 0.5,
                                  hint="Hole diameter = spacing − web")],
             "edges": _ALL_EDGES, "rounding": False},
    "triangles": {"label": "Triangles", "description": "Faceted triangular lattice",
                  "family": "lattice", "defaults": {"pitch": 12.0, "angle": 0.0},
                  "controls": [_slider("pitch", "Triangle size", 8.0, 20.0, 0.5, hint="Side length of each tile"),
                               _slider("angle", "Rotation", 0.0, 60.0, 5.0, unit="°")],
                  "edges": _ALL_EDGES, "rounding": True},
    "grid": {"label": "Diamond grid", "description": "Crisp angled cross-mesh",
             "family": "lattice", "defaults": {"pitch": 8.5, "angle": 45.0},
             "controls": [_slider("pitch", "Cell spacing", 5.5, 16.0, 0.5, hint=_PITCH_HINT),
                          _slider("angle", "Angle", 0.0, 90.0, 5.0, unit="°")],
             "edges": _ALL_EDGES, "rounding": True},
    "voronoi": {"label": "Voronoi", "description": "Organic cellular lattice",
                "family": "lattice", "defaults": {"pitch": 11.0, "seed": 42, "relax": 0},
                "controls": [_slider("pitch", "Cell size", 7.0, 18.0, 0.5),
                             _slider("seed", "Variation", 1, 99, 1, unit="", hint="A different random layout"),
                             _slider("relax", "Regularity", 0, 4, 1, unit="", hint="Higher = more even cells")],
                "edges": _ALL_EDGES, "rounding": True},
    "waves": {"label": "Waves", "description": "Flowing sine-wave slots",
              "family": "stripe", "defaults": {"pitch": 7.0, "amplitude": 3.5, "wavelength": 28.0},
              "controls": _STRIPE + [_slider("wavelength", "Wavelength", 12.0, 60.0, 1.0)],
              "edges": [], "rounding": True},
    "chevron": {"label": "Chevron", "description": "Sharp zig-zag slots",
                "family": "stripe", "defaults": {"pitch": 7.0, "amplitude": 3.5, "wavelength": 20.0},
                "controls": _STRIPE + [_slider("wavelength", "Zig-zag length", 10.0, 60.0, 1.0)],
                "edges": [], "rounding": True},
    "text": {"label": "Text", "description": "Lettering with stencil bridges",
             "family": "emblem",
             "defaults": {"text": "CASECRAFT", "font": "Arial", "size": 0.65, "rotation": 0.0, "bold": True,
                          "offset": [0.0, 0.0]},
             "controls": [{"key": "text", "label": "Text", "kind": "text", "max_length": 24},
                          {"key": "font", "label": "Font", "kind": "select", "options": list(FONTS)},
                          {"key": "bold", "label": "Bold", "kind": "toggle"},
                          _PLACEMENT[0],
                          _slider("rotation", "Rotation", -90.0, 90.0, 5.0, unit="°"),
                          _PLACEMENT[1]],
             "edges": [], "rounding": False},
    "svg": {"label": "SVG art", "description": "Your own vector artwork",
            "family": "emblem", "defaults": {"svg": STAR_SVG, "size": 0.6, "rotation": 0.0, "offset": [0.0, 0.0]},
            "controls": [{"key": "svg", "label": "Artwork", "kind": "svg"},
                         _PLACEMENT[0],
                         _slider("rotation", "Rotation", -180.0, 180.0, 5.0, unit="°"),
                         _PLACEMENT[1]],
            "edges": [], "rounding": False},
}

EDGE_SPECS = [
    {"id": "clip", "label": "Clip", "description": "Cells are cut off at the border"},
    {"id": "whole", "label": "Whole cells", "description": "Only complete cells: a clean, solid border"},
    {"id": "fade", "label": "Fade", "description": "Cells shrink towards the border"},
]
SHARED_CONTROLS = {
    "corner_radius": _slider("corner_radius", "Corner rounding", 0.0, 3.0, 0.1,
                             hint="Softer, stronger cut-out corners (adds 3D build time)"),
    "fade_width": _slider("fade_width", "Fade distance", 5.0, 40.0, 1.0,
                          hint="How far from the border the cells start to shrink"),
    "margin": _slider("margin", "Edge margin", 1.5, 10.0, 0.5),
    "web": _slider("web", "Min web ligament", 1.0, 4.0, 0.1),
}


def public_specs() -> dict:
    """JSON-able pattern metadata for the UI (GET /api/patterns)."""
    return {
        "types": [{"id": k, **v} for k, v in PATTERN_SPECS.items()],
        "edges": EDGE_SPECS,
        "shared": SHARED_CONTROLS,
        "fonts": list(FONTS),
    }


# ----------------------------------------------------------------------------- UI preview
def _ring_path(coords, nd: int) -> str:
    # back view: the design's +X appears on the LEFT; SVG y grows downwards
    pts = [f"{-x:.{nd}f} {-y:.{nd}f}" for x, y in list(coords)[:-1]]
    return "M" + "L".join(pts) + "Z" if len(pts) >= 3 else ""


def _path(geoms, nd: int = 2, simplify: float = 0.0) -> str:
    """SVG path data (back view) for polygons; render with fill-rule evenodd."""
    if not isinstance(geoms, (list, tuple)):
        geoms = [geoms]
    out = []
    for geom in geoms:
        for g in _parts(geom):
            if g.geom_type != "Polygon":
                continue
            if simplify:
                g = g.simplify(simplify, preserve_topology=True)
            out.append(_ring_path(g.exterior.coords, nd))
            out.extend(_ring_path(i.coords, nd) for i in g.interiors)
    return "".join(out)


def _camera_ring_poly(p: Preset):
    """Camera ring as seen from the back: bezel flange minus the clear aperture at the outer face."""
    cx, cy = p.camera_center()
    cw, ch, cr = camera_cutout_dims(p)
    bw = p.style.camera_bezel_width
    _, (ow, oh, orad, ox, oy) = p.aperture_profiles()
    flange = rrect_poly(cw + 2 * bw, ch + 2 * bw, cr + bw, cx, cy)
    return flange.difference(rrect_poly(ow, oh, orad, cx + ox, cy + oy))


def _frame(p: Preset, nd: int = 2, simplify: float = 0.0) -> dict:
    outer = plate_outline_poly(p, p.outer_offset)
    plate = plate_outline_poly(p, p.plate_body_offset)
    cam = camera_cutout_poly(p)
    minx, miny, maxx, maxy = outer.bounds
    pad = 1.0
    return {
        "view": "back",
        "viewBox": [round(-maxx - pad, 2), round(-maxy - pad, 2),
                    round(maxx - minx + 2 * pad, 2), round(maxy - miny + 2 * pad, 2)],
        "frame": _path(outer.difference(plate_outline_poly(p, p.rear_opening_offset)), nd, simplify),
        "plate": _path(plate.difference(cam), nd, simplify),
        "camera": _path(cam, nd, simplify),
        "ring": _path(_camera_ring_poly(p), nd, simplify),
        "magsafe": _path(magsafe_ring_poly(p), nd, simplify) if p.style.magsafe_ring else "",
    }


def pattern_preview(p: Preset) -> dict:
    """Back view of the backplate for the live 2D preview: bumper rim, plate, camera cutout,
    MagSafe ring, the cut-outs, and for through-cuts the pieces that would fall out (`islands`)
    and ligaments thinner than one extrusion (`thin`). A design error (MagSafe clash, loose
    pieces, unreadable artwork) is reported in `error` instead of raising."""
    pat = p.pattern
    out = _frame(p)
    out.update({"type": pat.type, "mode": pat.mode, "cuts": "", "islands": "", "thin": "",
                "stats": {"cuts": 0, "open_area_pct": 0.0},
                "connectivity": {"islands": 0, "thin_necks": 0}, "error": None,
                "warnings": [w for w in p.warnings() if w.startswith(("pattern", pat.type))]})
    try:
        polys = pattern_polys(p)
    except ParamError as exc:
        out["error"] = str(exc)
        return out
    if not polys:
        return out
    plate_area = plate_outline_poly(p, p.plate_body_offset).difference(camera_cutout_poly(p)).area
    out["cuts"] = _path(polys)
    out["stats"] = {"cuts": len(polys), "open_area_pct": round(100 * sum(g.area for g in polys) / plate_area, 1)}
    if pat.mode == "through":
        regions = _material_regions(p, polys)
        out["islands"] = _path(regions[1:])
        out["thin"] = _path(thin_ligaments(regions[0])) if regions else ""
        conn = through_cut_connectivity(p, polys)
        out["connectivity"] = {"islands": len(conn["islands"]), "thin_necks": conn["thin_necks"]}
        try:
            check_through_cut(p, polys)
        except ParamError as exc:
            out["error"] = str(exc)
    return out


def pattern_gallery(p: Preset) -> dict:
    """Thumbnail of every pattern type on this phone, with the current finish, border, rounding,
    margin and web but each type's default parameters. A type that is not valid with those
    settings maps to None (the UI falls back to an icon)."""
    out = _frame(p, nd=1, simplify=0.2)
    types = {}
    for t, spec in PATTERN_SPECS.items():
        q = dataclasses.replace(p, pattern=dataclasses.replace(p.pattern, type=t, params=dict(spec["defaults"])))
        if t == "solid":
            types[t] = {"cuts": ""}
            continue
        if q.check()[0]:
            types[t] = None
            continue
        try:
            types[t] = {"cuts": _path(pattern_polys(q), nd=1, simplify=0.15)}
        except ParamError:
            types[t] = None
    out["types"] = types
    return out
