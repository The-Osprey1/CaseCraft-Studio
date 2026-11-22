"""Parameter model, validation and derived mechanical dimensions.

Coordinate convention (design pose, all mm):
  * Origin = centre of the phone's back face, projected onto the backplate.
  * +Y = towards the top of the phone, +X = phone's RIGHT as seen from the FRONT.
  * Z = 0 is the OUTER face of the backplate; the phone sits at +Z; screen faces +Z.
  * Camera x/y are measured on the BACK view from its top-left corner (as on spec sheets).
  * Button `pos` = distance from top edge (left/right sides) or from front-view left edge
    (top/bottom sides) to the START of the button.  Port `center` = signed offset from the
    phone centre along the edge (+X for top/bottom, +Y for left/right).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

SIDES = ("left", "right", "top", "bottom")
PATTERN_DEFAULT_PITCH = {"hex": 9.0, "voronoi": 11.0, "grid": 8.5, "waves": 7.0,
                         "dots": 7.0, "triangles": 12.0, "chevron": 7.0}
MIN_PATTERN_PITCH = 3.0   # bounds the cell count (and loop count) of every lattice generator
MIN_PATTERN_WEB = 0.4     # one extrusion width
MIN_FLOOR = 0.6           # thinnest backplate skin left under a deboss/inlay or pocket
MAX_TEXT_LEN = 64
MAX_FONT_LEN = 64
MIN_WALL = 1.0            # thinnest TPU side wall accepted
PATTERN_TYPES = ("solid", "hex", "voronoi", "grid", "waves", "svg", "text", "dots", "triangles", "chevron")
PATTERN_MODES = ("through", "deboss", "inlay")
# How lattice patterns meet the border of the patterned area: clip (cells cut at the border, the
# original behaviour), whole (only complete cells) or fade (cells shrink towards the border).
EDGE_MODES = ("clip", "whole", "fade")
MAX_CORNER_RADIUS = 5.0
FADE_WIDTH_RANGE = (2.0, 60.0)
STRIPE_SHAPES = {"waves": "sine", "chevron": "chevron"}
# (name, hard min, hard max, recommended min, recommended max). Hard limits match the JSON
# schema; the recommended band is CaseCraft's default tuning range, NOT a physically validated
# tolerance -- outside it we warn and point at the fit-test coupon.
CLEARANCE_LIMITS = (
    ("frame_to_phone_offset", 0.0, 1.0, 0.10, 0.40),
    ("backplate_snap_clearance", 0.05, 0.4, 0.10, 0.25),
    ("button_clearance", 0.05, 0.5, 0.15, 0.35),
    ("camera_ring_clearance", 0.05, 0.4, 0.10, 0.25),
)


def stripe_cos(amplitude: float, wavelength: float, shape: str = "sine") -> float:
    """cos of the steepest slope of a stripe pattern's bands: the sine of `waves` (max slope
    2*pi*A/L) or the straight zig-zag of `chevron` (constant slope 4*A/L)."""
    wl = max(wavelength, 6.0)
    slope = 4 * amplitude / wl if shape == "chevron" else 2 * math.pi * amplitude / wl
    return math.cos(math.atan(slope))


def wave_cos(amplitude: float, wavelength: float) -> float:
    """cos of the steepest slope of the waves pattern's sine bands."""
    return stripe_cos(amplitude, wavelength, "sine")


def wave_min_rib(pitch: float, web: float, amplitude: float, wavelength: float, shape: str = "sine") -> float:
    """Narrowest rib left between stripe bands (slot width is clamped to >= 1 mm)."""
    spacing = pitch * stripe_cos(amplitude, wavelength, shape)
    slot = max(1.0, spacing - web)
    return spacing - slot


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class ParamError(ValueError):
    pass


def _build_camera(data: dict | None):
    data = dict(data or {})
    opening = data.pop("opening", None)
    cam = _build(Camera, data)
    cam.opening = _build(CameraOpening, opening) if opening is not None else None
    return cam


def _build(cls, data: dict | None):
    data = dict(data or {})
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ParamError(f"{cls.__name__}: unknown keys {sorted(unknown)}")
    return cls(**data)


@dataclass
class Body:
    length: float = 146.6
    width: float = 70.6
    thickness: float = 8.25
    corner_radius: float = 11.0


@dataclass
class CameraOpening:
    """Optional clear aperture at the case's OUTER face (ring bezel / unibody back). The camera
    island's width/height/radius stay the profile at its BASE (against the phone back); the
    aperture is lofted between the two, so a bump that is wider at its base, or an opening that
    flares for a wide-angle lens, no longer forces one oversized cutout. dx/dy shift the opening
    centre from the island centre, measured like camera.x/y on the BACK view (+dx right, +dy down)."""
    width: float = 0.0
    height: float = 0.0
    radius: float = 0.0
    dx: float = 0.0
    dy: float = 0.0


@dataclass
class Camera:
    x: float = 3.5
    y: float = 3.5
    width: float = 36.0       # island at its base (phone back)
    height: float = 38.0
    radius: float = 9.0
    opening: CameraOpening | None = None   # optional outer-face profile (see CameraOpening)


@dataclass
class Button:
    id: str = "button"
    side: str = "right"
    pos: float = 40.0
    length: float = 12.0


@dataclass
class Port:
    id: str = "usbc"
    side: str = "bottom"
    center: float = 0.0
    width: float = 13.0
    height: float = 7.0
    radius: float = 3.5
    z_offset: float = 0.0  # relative to mid-thickness of phone


@dataclass
class Clearances:
    frame_to_phone_offset: float = 0.25
    backplate_snap_clearance: float = 0.15
    button_clearance: float = 0.2
    camera_ring_clearance: float = 0.15


@dataclass
class Style:
    frame_wall: float = 1.6
    front_lip: float = 1.2           # inward overhang over the screen edge
    front_lip_thickness: float = 2.4  # 45deg ramp (o+front_lip) + flat land at the opening
    backplate_thickness: float = 1.8  # 1.6 - 2.0
    tongue_height: float = 0.8
    groove_depth: float = 0.9         # into the TPU wall beyond the cavity
    snap_engage: float = 0.6          # how far the rear TPU lip is inboard of the groove
    button_height: float = 3.0
    button_cap_height: float = 0.8
    button_flange_overhang: float = 0.8
    button_flange_thickness: float = 0.6
    button_travel: float = 0.3
    camera_cutout_margin: float = 1.6  # backplate cutout = island + margin per side
    camera_aperture_margin: float = 0.2
    camera_bezel_height: float = 1.5
    camera_bezel_width: float = 1.2
    camera_bead: float = 0.3
    magsafe_ring: bool = False
    magsafe_depth: float = 0.75
    magsafe_offset_y: float = 0.0     # ring centre shift along Y (- = towards bottom); match the phone's charging coil


@dataclass
class Pattern:
    type: str = "solid"          # solid | hex | voronoi | grid | waves | svg | text | dots | triangles | chevron
    mode: str = "through"        # through | deboss | inlay
    depth: float = 0.8           # deboss / inlay depth
    margin: float = 3.0          # inset from plate edge and camera cutout
    web: float = 1.6             # min material between cut-outs
    stencil_bridges: bool = True
    edge: str = "clip"           # lattices: clip (cells cut at the border) | whole | fade
    corner_radius: float = 0.0   # rounds the corners of lattice/stripe cut-outs (mm); 0 = sharp
    fade_width: float = 15.0     # edge == "fade": distance from the border over which cells shrink
    # hex/dots: pitch | voronoi: pitch, seed, relax | grid/triangles: pitch, angle |
    # waves/chevron: pitch, amplitude, wavelength | svg: svg, size, rotation, offset |
    # text: text, font, font_size, size, rotation, bold, offset
    params: dict[str, Any] = field(default_factory=dict)


VERIFICATION_LEVELS = ("approximate", "dimensionally_verified", "physically_fit_tested")
FIT_TEST_STATUSES = ("untested", "passed", "failed")


@dataclass
class Verification:
    """Optional provenance of a device preset. Defaults describe an unverified preset, so old
    preset files (without this block) load as `approximate`. Never fill these in without
    evidence: `physically_fit_tested` means a printed case was fitted to the real device."""
    level: str = "approximate"         # approximate | dimensionally_verified | physically_fit_tested
    source: str = ""                   # where the dimensions came from (spec sheet, calipers, CAD, ...)
    fit_test: str = "untested"         # untested | passed | failed  (physical fit test of a printed part)
    notes: str = ""
    unverified_features: list[str] = field(default_factory=list)   # e.g. ["camera", "buttons"]


@dataclass
class Preset:
    id: str = "custom"
    name: str = "Custom"
    body: Body = field(default_factory=Body)
    camera: Camera = field(default_factory=Camera)
    buttons: list[Button] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    clearances: Clearances = field(default_factory=Clearances)
    style: Style = field(default_factory=Style)
    pattern: Pattern = field(default_factory=Pattern)
    verification: Verification = field(default_factory=Verification)

    # ---- construction -------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "Preset":
        if not isinstance(d, dict):
            raise ParamError(f"Preset: expected a JSON object, got {type(d).__name__}")
        d = dict(d)
        p = cls(
            id=d.pop("id", "custom"),
            name=d.pop("name", "Custom"),
            body=_build(Body, d.pop("body", None)),
            camera=_build_camera(d.pop("camera", None)),
            buttons=[_build(Button, b) for b in d.pop("buttons", [])],
            ports=[_build(Port, b) for b in d.pop("ports", [])],
            clearances=_build(Clearances, d.pop("clearances", None)),
            style=_build(Style, d.pop("style", None)),
            pattern=_build(Pattern, d.pop("pattern", None)),
            verification=_build(Verification, d.pop("verification", None)),
        )
        d.pop("$schema", None)
        if d:
            raise ParamError(f"Preset: unknown keys {sorted(d)}")
        p.validate()
        return p

    @classmethod
    def load(cls, path_or_id: str | Path) -> "Preset":
        path = Path(path_or_id)
        if not path.exists():
            import appdirs   # local import: params stays importable on its own
            path = appdirs.resource_dir() / "presets" / f"{path_or_id}.json"
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    # ---- derived dims -------------------------------------------------
    @property
    def L(self): return self.body.length
    @property
    def W(self): return self.body.width
    @property
    def T(self): return self.body.thickness
    @property
    def o(self): return self.clearances.frame_to_phone_offset
    @property
    def sc(self): return self.clearances.backplate_snap_clearance
    @property
    def bp_t(self): return self.style.backplate_thickness
    @property
    def lip_t(self): return self.style.front_lip_thickness
    @property
    def H(self):
        """Total frame height (z = 0 rear .. H front lip face)."""
        return self.bp_t + self.T + self.o + self.lip_t
    @property
    def cavity_offset(self): return self.o  # relative to phone outline
    @property
    def groove_offset(self): return self.o + self.style.groove_depth
    @property
    def rear_opening_offset(self): return self.groove_offset - self.style.snap_engage
    @property
    def plate_body_offset(self): return self.rear_opening_offset - self.sc
    @property
    def tongue_offset(self): return self.groove_offset - self.sc
    @property
    def outer_offset(self): return self.o + self.style.frame_wall

    def aperture_profiles(self):
        """(base, outer) clear camera apertures as (w, h, r, ox, oy), offsets relative to the
        island centre in DESIGN coordinates. Without an opening both are the island + margin."""
        c, m = self.camera, self.style.camera_aperture_margin
        base = (c.width + 2 * m, c.height + 2 * m, c.radius + m, 0.0, 0.0)
        if c.opening is None:
            return base, base
        o = c.opening
        return base, (o.width, o.height, o.radius, -o.dx, -o.dy)   # back view -> design coords

    def camera_center(self) -> tuple[float, float]:
        c = self.camera
        return (self.W / 2 - (c.x + c.width / 2), self.L / 2 - (c.y + c.height / 2))

    # ---- validation ---------------------------------------------------
    # Single authoritative source for parameter rules. `check()` returns (errors, warnings):
    # errors make a design unbuildable/unprintable and are raised by `validate()` (-> HTTP 422,
    # CLI exit 2); warnings are legitimate-but-risky choices surfaced to the user.
    def validate(self) -> None:
        errs, _ = self.check()
        if errs:
            raise ParamError("; ".join(errs))

    def warnings(self) -> list[str]:
        return self.check()[1]

    def check(self) -> tuple[list[str], list[str]]:
        errs = self._type_errors()
        if errs:                      # geometry rules below assume finite numbers
            return errs, []
        warns: list[str] = []
        b, s, c = self.body, self.style, self.clearances
        for n, v in (("length", b.length), ("width", b.width), ("thickness", b.thickness)):
            if v <= 0: errs.append(f"body.{n} must be > 0")
        if b.corner_radius < 0 or b.corner_radius > min(b.length, b.width) / 2:
            errs.append("body.corner_radius out of range")
        if errs:
            return errs, warns
        # -- clearances: hard limits (schema) + recommended tuning range (warnings)
        for name, lo, hi, rlo, rhi in CLEARANCE_LIMITS:
            v = getattr(c, name)
            if not lo <= v <= hi:
                errs.append(f"clearances.{name} must be within {lo:g}-{hi:g} mm")
            elif not rlo <= v <= rhi:
                side = "below" if v < rlo else "above"
                warns.append(f"clearances.{name} {v:g} mm is {side} the recommended range "
                             f"({rlo:g}-{rhi:g} mm); print a fit-test coupon before a full case")
        # -- positive style dimensions
        for name in ("frame_wall", "front_lip", "front_lip_thickness", "tongue_height", "groove_depth",
                     "snap_engage", "button_height", "button_cap_height", "button_flange_overhang",
                     "button_flange_thickness", "camera_bezel_height", "camera_bezel_width"):
            if getattr(s, name) <= 0:
                errs.append(f"style.{name} must be > 0")
        for name in ("button_travel", "camera_cutout_margin", "camera_aperture_margin", "camera_bead"):
            if getattr(s, name) < 0:
                errs.append(f"style.{name} must be >= 0")
        if errs:
            return errs, warns
        # -- walls, snap joint and screen lip
        if s.frame_wall < MIN_WALL:
            errs.append(f"style.frame_wall must be >= {MIN_WALL} mm")
        if not 1.6 <= s.backplate_thickness <= 2.0:
            errs.append("style.backplate_thickness must be within 1.6-2.0 mm")
        if s.tongue_height >= s.backplate_thickness - 0.6:
            errs.append("tongue_height leaves < 0.6 mm plate body")
        if s.groove_depth > 0.6 * s.frame_wall:
            errs.append("groove_depth > 60% of frame_wall (TPU wall too thin)")
        if s.frame_wall - s.groove_depth < MIN_FLOOR:
            errs.append(f"frame_wall - groove_depth leaves < {MIN_FLOOR} mm TPU behind the retention groove")
        if s.backplate_thickness - s.tongue_height - c.backplate_snap_clearance < MIN_FLOOR:
            errs.append(f"rear retaining lip under the groove is < {MIN_FLOOR} mm thick "
                        "(reduce tongue_height or snap clearance)")
        if s.snap_engage <= c.backplate_snap_clearance + 0.2:
            errs.append("snap_engage must exceed snap clearance by >= 0.2 mm")
        if s.snap_engage >= s.groove_depth:
            errs.append("snap_engage must be < groove_depth")
        if s.front_lip_thickness < self.o + s.front_lip + 0.6:
            errs.append("front_lip_thickness must cover the 45deg lip ramp (o + front_lip) plus >= 0.6 mm land")
        if s.front_lip < 0.6:
            warns.append(f"style.front_lip {s.front_lip:g} mm is a very narrow screen lip; the phone may pop out")
        # -- buttons
        if s.button_height > b.thickness - 1.0:
            errs.append("button_height too large for phone thickness")
        if s.frame_wall - (s.button_flange_thickness + s.button_travel) < 0.6:
            errs.append("button pocket leaves < 0.6 mm TPU retaining ring")
        pocket_half = s.button_height / 2 + s.button_flange_overhang + c.button_clearance
        if pocket_half > b.thickness / 2 - c.backplate_snap_clearance:
            errs.append("button flange pocket is taller than the side wall between groove and screen lip "
                        "(reduce button_height or button_flange_overhang)")
        spans: dict[str, list] = {sd: [] for sd in SIDES}
        for bt in self.buttons:
            if bt.side not in SIDES:
                errs.append(f"button {bt.id}: bad side")
                continue
            if bt.length <= 0:
                errs.append(f"button {bt.id}: length must be > 0")
                continue
            edge = b.length if bt.side in ("left", "right") else b.width
            if bt.pos < b.corner_radius or bt.pos + bt.length > edge - b.corner_radius:
                errs.append(f"button {bt.id} overlaps a corner (pos/length)")
            grow = s.button_flange_overhang + c.button_clearance
            spans[bt.side].append((bt.pos - grow, bt.pos + bt.length + grow, f"button {bt.id}"))
        for sd, items in spans.items():
            items.sort()
            for (a0, a1, an), (b0, b1, bn) in zip(items, items[1:]):
                gap = b0 - a1
                if gap < 0:
                    errs.append(f"{an} and {bn} pockets overlap on the {sd} side")
                elif gap < 1.0:
                    warns.append(f"only {gap:.2f} mm of TPU between the {an} and {bn} pockets")
        # -- ports
        port_spans: dict[str, list] = {sd: [] for sd in SIDES}
        for pt in self.ports:
            if pt.side not in SIDES:
                errs.append(f"port {pt.id}: bad side")
                continue
            if pt.width <= 0 or pt.height <= 0 or pt.radius < 0:
                errs.append(f"port {pt.id}: width/height must be > 0 and radius >= 0")
                continue
            edge = b.length if pt.side in ("left", "right") else b.width
            half = edge / 2
            reach = abs(pt.center) + pt.width / 2
            if reach > half:
                errs.append(f"port {pt.id} extends past the end of the {pt.side} edge")
            elif reach > half - b.corner_radius:
                warns.append(f"port {pt.id} runs into the rounded corner of the {pt.side} edge")
            if pt.height / 2 + abs(pt.z_offset) > b.thickness / 2 + self.o:
                errs.append(f"port {pt.id} opening cuts into the screen lip or backplate groove "
                            "(reduce height or z_offset)")
            # along-edge coordinate measured like button pos (from the top / front-view left)
            along = (half - pt.center) if pt.side in ("left", "right") else (half + pt.center)
            port_spans[pt.side].append((along - pt.width / 2, along + pt.width / 2, f"port {pt.id}"))
        for sd in SIDES:
            ports = sorted(port_spans[sd])
            for (a0, a1, an), (b0, b1, bn) in zip(ports, ports[1:]):
                if b0 < a1:
                    warns.append(f"{an} and {bn} overlap and will merge into one opening")
            for p0, p1, pn in ports:
                for b0, b1, bn in spans[sd]:
                    if p0 < b1 and b0 < p1:
                        errs.append(f"{pn} overlaps the {bn} pocket on the {sd} side")
        # -- camera
        cam = self.camera
        if cam.width <= 0 or cam.height <= 0 or cam.radius < 0:
            errs.append("camera width/height must be > 0 and radius >= 0")
        else:
            cx, cy = self.camera_center()
            m = s.camera_cutout_margin
            bz = s.camera_bezel_width
            if abs(cx) + cam.width / 2 + m + bz > b.width / 2 - 0.3 or abs(cy) + cam.height / 2 + m + bz > b.length / 2 - 0.3:
                errs.append("camera island (with margin) plus bezel must stay inside the phone outline")
            if cam.opening is not None:
                e, w = self._camera_opening_rules()
                errs += e
                warns += w
        # -- MagSafe, pattern
        if s.magsafe_ring and (s.backplate_thickness - s.magsafe_depth < 0.7 or s.magsafe_depth <= 0):
            errs.append("magsafe_depth must leave >= 0.7 mm backplate floor")
        if self.pattern.type not in PATTERN_TYPES:
            errs.append("pattern.type must be " + "|".join(PATTERN_TYPES))
        if self.pattern.mode not in PATTERN_MODES:
            errs.append("pattern.mode must be " + "|".join(PATTERN_MODES))
        errs += self._pattern_errors()
        if (not errs and self.pattern.type not in ("solid", "svg", "text")
                and self.pattern.web < 2 * MIN_PATTERN_WEB):
            warns.append(f"pattern.web {self.pattern.web:g} mm is below two extrusion widths "
                         f"({2 * MIN_PATTERN_WEB:g} mm); the lattice ribs will be fragile")
        if not errs and self.pattern.type in STRIPE_SHAPES:
            pr, t = self.pattern.params, self.pattern.type
            rib = wave_min_rib(pr.get("pitch", PATTERN_DEFAULT_PITCH[t]), self.pattern.web,
                               pr.get("amplitude", 3.5), pr.get("wavelength", 28.0), STRIPE_SHAPES[t])
            if rib < self.pattern.web - 1e-6:
                warns.append(f"{t}: ribs narrow to {rib:.2f} mm at the steepest point "
                             f"(below the {self.pattern.web:g} mm web); increase pitch or wavelength")
        return errs, warns

    def _camera_opening_rules(self) -> tuple[list[str], list[str]]:
        """Keep the lofted aperture buildable and printable: positive profile, walls left in the
        ring flange and spigot, and no inward lean steeper than 45 deg (the ring prints outer
        face down, the unibody back-down)."""
        errs, warns = [], []
        o, s, c = self.camera.opening, self.style, self.clearances
        if o.width <= 0 or o.height <= 0 or o.radius < 0:
            return ["camera.opening width/height must be > 0 and radius >= 0"], []
        if o.radius > min(o.width, o.height) / 2:
            errs.append("camera.opening.radius must be <= half the opening width/height")
        base, outer = self.aperture_profiles()
        cut_w = self.camera.width + 2 * s.camera_cutout_margin
        cut_h = self.camera.height + 2 * s.camera_cutout_margin
        bz, bp = s.camera_bezel_height, self.bp_t
        # flange wall at the outer face
        for half_out, size, off, axis in ((cut_w / 2 + s.camera_bezel_width, outer[0], outer[3], "width"),
                                          (cut_h / 2 + s.camera_bezel_width, outer[1], outer[4], "height")):
            if half_out - (abs(off) + size / 2) < 0.8:
                errs.append(f"camera.opening leaves < 0.8 mm of camera-ring bezel ({axis}); reduce the opening or its offset")
        # spigot wall where the ring passes through the backplate (z = 0)
        t = bz / (bz + bp)
        mid = [outer[i] + t * (base[i] - outer[i]) for i in range(5)]
        for half_sp, size, off, axis in ((cut_w / 2 - c.camera_ring_clearance, mid[0], mid[3], "width"),
                                         (cut_h / 2 - c.camera_ring_clearance, mid[1], mid[4], "height")):
            if half_sp - (abs(off) + size / 2) < 0.6:
                errs.append(f"camera.opening leaves < 0.6 mm of camera-ring wall inside the backplate ({axis}); "
                            "reduce the flare or increase style.camera_cutout_margin")
        # inward lean of the aperture wall going up from the outer face (overhang)
        lean = max(-base[0] / 2 - (outer[3] - outer[0] / 2), (outer[3] + outer[0] / 2) - base[0] / 2,
                   -base[1] / 2 - (outer[4] - outer[1] / 2), (outer[4] + outer[1] / 2) - base[1] / 2)
        if lean > bz + bp:
            errs.append(f"camera.opening flares {lean:.2f} mm beyond the base over {bz + bp:.2f} mm of ring height "
                        "(> 45 deg overhang); reduce the flare")
        elif lean > bp:
            warns.append(f"Unibody: the camera opening flare ({lean:.2f} mm) is steeper than 45 deg across the "
                         f"{bp:g} mm floor and will need support there")
        return errs, warns

    def _type_errors(self) -> list[str]:
        """Every numeric field must be a finite number and every flag a bool, whatever the source
        (JSON, form input, CLI). Catches NaN/inf/strings before any geometry is attempted."""
        errs = []
        groups = [("body", self.body), ("camera", self.camera), ("clearances", self.clearances),
                  ("style", self.style), ("pattern", self.pattern)]
        groups += [(f"buttons[{i}]", bt) for i, bt in enumerate(self.buttons)]
        groups += [(f"ports[{i}]", pt) for i, pt in enumerate(self.ports)]
        groups += [("verification", self.verification)]
        if self.camera.opening is not None:
            groups += [("camera.opening", self.camera.opening)]
        v = self.verification
        if v.level not in VERIFICATION_LEVELS:
            errs.append("verification.level must be " + "|".join(VERIFICATION_LEVELS))
        if v.fit_test not in FIT_TEST_STATUSES:
            errs.append("verification.fit_test must be " + "|".join(FIT_TEST_STATUSES))
        if v.level == "physically_fit_tested" and v.fit_test != "passed":
            errs.append("verification.level 'physically_fit_tested' requires fit_test 'passed'")
        if not (isinstance(v.unverified_features, list) and all(isinstance(x, str) for x in v.unverified_features)):
            errs.append("verification.unverified_features must be a list of strings")
        for gname, obj in groups:
            for f in fields(obj):
                v = getattr(obj, f.name)
                if f.type in ("float", float):
                    if not _finite(v):
                        errs.append(f"{gname}.{f.name} must be a finite number")
                elif f.type in ("bool", bool):
                    if not isinstance(v, bool):
                        errs.append(f"{gname}.{f.name} must be true or false")
                elif f.type in ("str", str):
                    if not isinstance(v, str):
                        errs.append(f"{gname}.{f.name} must be a string")
        return errs

    def _pattern_errors(self) -> list[str]:
        """Pattern numbers drive unbounded `while` loops and boolean depths, so bound them here."""
        pat, errs = self.pattern, []
        if not (_finite(pat.web) and pat.web >= MIN_PATTERN_WEB):
            errs.append(f"pattern.web must be >= {MIN_PATTERN_WEB} mm")
        if not (_finite(pat.margin) and pat.margin >= 0):
            errs.append("pattern.margin must be >= 0")
        if pat.edge not in EDGE_MODES:
            errs.append("pattern.edge must be " + "|".join(EDGE_MODES))
        if not (_finite(pat.corner_radius) and 0 <= pat.corner_radius <= MAX_CORNER_RADIUS):
            errs.append(f"pattern.corner_radius must be within 0-{MAX_CORNER_RADIUS:g} mm")
        lo, hi = FADE_WIDTH_RANGE
        if not (_finite(pat.fade_width) and lo <= pat.fade_width <= hi):
            errs.append(f"pattern.fade_width must be within {lo:g}-{hi:g} mm")
        if not isinstance(pat.params, dict):
            return errs + ["pattern.params must be an object"]
        pr = pat.params
        pitch = None
        if pat.type in PATTERN_DEFAULT_PITCH:
            pitch = pr.get("pitch", PATTERN_DEFAULT_PITCH[pat.type])
            if not (_finite(pitch) and pitch >= MIN_PATTERN_PITCH):
                errs.append(f"pattern.params.pitch must be a number >= {MIN_PATTERN_PITCH} mm")
                pitch = None
            elif _finite(pat.web) and pitch <= pat.web:
                errs.append("pattern.params.pitch must be larger than pattern.web")
                pitch = None
        if pitch is not None and _finite(pat.web):
            if pat.type == "triangles" and pitch < math.sqrt(3) * pat.web + 1.0:
                errs.append(f"triangles: pattern.params.pitch must be >= {math.sqrt(3) * pat.web + 1.0:.2f} mm "
                            f"for a {pat.web:g} mm web (the cut-outs would vanish)")
            if pat.type == "dots" and pitch < pat.web + 1.0:
                errs.append("dots: pattern.params.pitch must exceed pattern.web by at least 1 mm")
        if pat.type in STRIPE_SHAPES:
            amp = pr.get("amplitude", 3.5)
            wl = pr.get("wavelength", 28.0)
            if not (_finite(amp) and 0 <= amp <= 50):
                errs.append("pattern.params.amplitude must be within 0-50 mm")
            if not (_finite(wl) and wl > 0):
                errs.append("pattern.params.wavelength must be > 0")
            elif _finite(amp) and pitch is not None and 0 <= amp <= 50:
                # rib between bands, measured perpendicular to the steepest part of the curve
                # (slots never go below 1 mm): see patterns._stripe_raw
                rib = wave_min_rib(pitch, pat.web, amp, wl, STRIPE_SHAPES[pat.type])
                if rib < MIN_PATTERN_WEB:
                    errs.append(f"{pat.type} too steep for this pitch: ribs would be {max(rib, 0):.2f} mm wide "
                                f"(< {MIN_PATTERN_WEB} mm); increase pitch or wavelength, or reduce amplitude")
        if pat.type in ("grid", "triangles") and not (_finite(pr.get("angle", 0.0)) and abs(pr.get("angle", 0.0)) <= 360):
            errs.append("pattern.params.angle must be a number within -360-360 degrees")
        if pat.type == "voronoi":
            if not _finite(pr.get("seed", 42)):
                errs.append("pattern.params.seed must be a number")
            relax = pr.get("relax", 0)
            if not (_finite(relax) and float(relax).is_integer() and 0 <= relax <= 5):
                errs.append("pattern.params.relax must be a whole number within 0-5")
        if pat.type in ("text", "svg"):
            errs += self._placement_errors(pr)
        if pat.type == "svg" and not (isinstance(pr.get("svg"), str) and pr["svg"].strip()):
            errs.append("pattern.params.svg must contain SVG markup (choose an emblem or upload a drawing)")
        if pat.type == "text":
            if len(str(pr.get("text", ""))) > MAX_TEXT_LEN:
                errs.append(f"pattern.params.text must be <= {MAX_TEXT_LEN} characters")
            font = pr.get("font", "Arial")
            if not (isinstance(font, str) and 0 < len(font) <= MAX_FONT_LEN):
                errs.append(f"pattern.params.font must be a font name of 1-{MAX_FONT_LEN} characters")
        if pat.type != "solid" and pat.mode in ("deboss", "inlay"):
            max_depth = self.style.backplate_thickness - MIN_FLOOR
            if not (_finite(pat.depth) and 0 < pat.depth <= max_depth):
                errs.append(f"pattern.depth must be within 0-{max_depth:.2f} mm "
                            f"(leaves >= {MIN_FLOOR} mm backplate floor)")
        return errs

    @staticmethod
    def _placement_errors(pr: dict) -> list[str]:
        """Size / rotation / offset of a text or SVG emblem: fraction of the patterned area,
        degrees, and mm from the plate centre in DESIGN coordinates (+X = the phone's right seen
        from the front, so +X moves the emblem LEFT on the back view; +Y = towards the top)."""
        errs = []
        size = pr.get("size", 0.7)
        if not (_finite(size) and 0 < size <= 1.5):
            errs.append("pattern.params.size must be within 0-1.5 (fraction of the patterned area)")
        rot = pr.get("rotation", 0.0)
        if not (_finite(rot) and abs(rot) <= 360):
            errs.append("pattern.params.rotation must be a number within -360-360 degrees")
        off = pr.get("offset", (0.0, 0.0))
        if not (isinstance(off, (list, tuple)) and len(off) == 2 and all(_finite(v) and abs(v) <= 100 for v in off)):
            errs.append("pattern.params.offset must be [x, y] in mm, each within -100-100")
        return errs
