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
PATTERN_DEFAULT_PITCH = {"hex": 9.0, "voronoi": 11.0, "grid": 8.5, "waves": 7.0}
MIN_PATTERN_PITCH = 3.0   # bounds the cell count (and loop count) of every lattice generator
MIN_PATTERN_WEB = 0.4     # one extrusion width
MIN_FLOOR = 0.6           # thinnest backplate skin left under a deboss/inlay or pocket
MAX_TEXT_LEN = 64
MIN_WALL = 1.0            # thinnest TPU side wall accepted
PATTERN_TYPES = ("solid", "hex", "voronoi", "grid", "waves", "svg", "text")
PATTERN_MODES = ("through", "deboss", "inlay")
# (name, hard min, hard max, recommended min, recommended max). Hard limits match the JSON
# schema; the recommended band is CaseCraft's default tuning range, NOT a physically validated
# tolerance -- outside it we warn and point at the fit-test coupon.
CLEARANCE_LIMITS = (
    ("frame_to_phone_offset", 0.0, 1.0, 0.10, 0.40),
    ("backplate_snap_clearance", 0.05, 0.4, 0.10, 0.25),
    ("button_clearance", 0.05, 0.5, 0.15, 0.35),
    ("camera_ring_clearance", 0.05, 0.4, 0.10, 0.25),
)


def wave_cos(amplitude: float, wavelength: float) -> float:
    """cos of the steepest slope of the waves pattern's sine bands."""
    return math.cos(math.atan(2 * math.pi * amplitude / max(wavelength, 6.0)))


def wave_min_rib(pitch: float, web: float, amplitude: float, wavelength: float) -> float:
    """Narrowest rib left between waves bands (slot width is clamped to >= 1 mm)."""
    spacing = pitch * wave_cos(amplitude, wavelength)
    slot = max(1.0, spacing - web)
    return spacing - slot


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class ParamError(ValueError):
    pass


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
class Camera:
    x: float = 3.5
    y: float = 3.5
    width: float = 36.0
    height: float = 38.0
    radius: float = 9.0


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
    type: str = "solid"          # solid | hex | voronoi | grid | waves | svg | text
    mode: str = "through"        # through | deboss | inlay
    depth: float = 0.8           # deboss / inlay depth
    margin: float = 3.0          # inset from plate edge and camera cutout
    web: float = 1.6             # min material between cut-outs
    stencil_bridges: bool = True
    params: dict[str, Any] = field(default_factory=dict)  # hex/voronoi: pitch | grid: pitch, angle | waves: pitch, amplitude, wavelength | svg: svg, size, offset | text: text, font, font_size, size, offset


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

    # ---- construction -------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "Preset":
        d = dict(d)
        p = cls(
            id=d.pop("id", "custom"),
            name=d.pop("name", "Custom"),
            body=_build(Body, d.pop("body", None)),
            camera=_build(Camera, d.pop("camera", None)),
            buttons=[_build(Button, b) for b in d.pop("buttons", [])],
            ports=[_build(Port, b) for b in d.pop("ports", [])],
            clearances=_build(Clearances, d.pop("clearances", None)),
            style=_build(Style, d.pop("style", None)),
            pattern=_build(Pattern, d.pop("pattern", None)),
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
            path = Path(__file__).parent / "presets" / f"{path_or_id}.json"
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
        if not errs and self.pattern.type == "waves":
            pr = self.pattern.params
            rib = wave_min_rib(pr.get("pitch", PATTERN_DEFAULT_PITCH["waves"]), self.pattern.web,
                               pr.get("amplitude", 3.5), pr.get("wavelength", 28.0))
            if rib < self.pattern.web - 1e-6:
                warns.append(f"waves: ribs narrow to {rib:.2f} mm at the steepest point "
                             f"(below the {self.pattern.web:g} mm web); increase pitch or wavelength")
        return errs, warns

    def _type_errors(self) -> list[str]:
        """Every numeric field must be a finite number and every flag a bool, whatever the source
        (JSON, form input, CLI). Catches NaN/inf/strings before any geometry is attempted."""
        errs = []
        groups = [("body", self.body), ("camera", self.camera), ("clearances", self.clearances),
                  ("style", self.style), ("pattern", self.pattern)]
        groups += [(f"buttons[{i}]", bt) for i, bt in enumerate(self.buttons)]
        groups += [(f"ports[{i}]", pt) for i, pt in enumerate(self.ports)]
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
        if not isinstance(pat.params, dict):
            return errs + ["pattern.params must be an object"]
        if pat.type in PATTERN_DEFAULT_PITCH:
            pitch = pat.params.get("pitch", PATTERN_DEFAULT_PITCH[pat.type])
            if not (_finite(pitch) and pitch >= MIN_PATTERN_PITCH):
                errs.append(f"pattern.params.pitch must be a number >= {MIN_PATTERN_PITCH} mm")
            elif _finite(pat.web) and pitch <= pat.web:
                errs.append("pattern.params.pitch must be larger than pattern.web")
        if pat.type == "waves":
            amp = pat.params.get("amplitude", 3.5)
            wl = pat.params.get("wavelength", 28.0)
            if not (_finite(amp) and 0 <= amp <= 50):
                errs.append("pattern.params.amplitude must be within 0-50 mm")
            if not (_finite(wl) and wl > 0):
                errs.append("pattern.params.wavelength must be > 0")
            elif _finite(amp) and _finite(pitch) and 0 <= amp <= 50:
                # rib between bands, measured perpendicular to the steepest part of the curve
                # (slots never go below 1 mm): see cad_engine._wave_polys
                rib = wave_min_rib(pitch, pat.web, amp, wl)
                if rib < MIN_PATTERN_WEB:
                    errs.append(f"waves too steep for this pitch: ribs would be {max(rib, 0):.2f} mm wide "
                                f"(< {MIN_PATTERN_WEB} mm); increase pitch or wavelength, or reduce amplitude")
        if pat.type == "text" and len(str(pat.params.get("text", ""))) > MAX_TEXT_LEN:
            errs.append(f"pattern.params.text must be <= {MAX_TEXT_LEN} characters")
        if pat.type != "solid" and pat.mode in ("deboss", "inlay"):
            max_depth = self.style.backplate_thickness - MIN_FLOOR
            if not (_finite(pat.depth) and 0 < pat.depth <= max_depth):
                errs.append(f"pattern.depth must be within 0-{max_depth:.2f} mm "
                            f"(leaves >= {MIN_FLOOR} mm backplate floor)")
        return errs
