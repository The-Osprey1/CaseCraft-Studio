// Slider ranges for the fit/snap settings that the CAD engine will actually accept with the rest
// of the current design. They mirror the interlocking rules in params.py (the server stays the
// authority and still validates everything); without them a slider could be dragged straight into
// an "invalid design" (e.g. a 1.4 mm wall under the default 0.9 mm retention groove).

const MIN_FLOOR = 0.6; // params.MIN_FLOOR: thinnest TPU / PLA skin
const STEP_EPS = 0.05; // strict inequalities keep one slider step of distance
const FP = 1e-4; // computed bounds stay a hair inside: the server compares in floating point
const PORT_FLARE_RISE = 1.04; // params.PORT_FLARE_RISE: a port flare's roof rises this much per mm of chamfer

/**
 * [min, max] on the slider's step grid: the fixed limits as they are, the limits that follow
 * from other settings rounded inwards. A design that is already inconsistent (an imported file)
 * keeps the fixed range, so the slider still works and the validation message explains.
 */
function range(fixedLo, derivedLo, fixedHi, derivedHi, step) {
  const q = (v) => Number((v / step).toFixed(6)); // 0.65 / 0.05 is 13.000000000000002 in floats
  const lo = Math.max(fixedLo, Math.ceil(q(derivedLo + FP)) * step);
  const hi = Math.min(fixedHi, Math.floor(q(derivedHi - FP)) * step);
  const r = (v) => Number(v.toFixed(4));
  return lo <= hi ? [r(lo), r(hi)] : [fixedLo, fixedHi];
}

/** {fieldName: [min, max]} for the Tolerances tab sliders, given the whole config. */
export function fitLimits(config) {
  const s = config.style;
  const c = config.clearances;
  const T = config.body.thickness;
  const o = c.frame_to_phone_offset;
  const sc = c.backplate_snap_clearance;
  const flangeHalf = s.button_height / 2 + s.button_flange_overhang;
  const portNeed = Math.max(
    -Infinity,
    ...(config.ports || []).map((p) => p.height / 2 + Math.abs(p.z_offset || 0) - T / 2)
  );
  const recess = config.pattern?.type !== "solid" && ["deboss", "inlay"].includes(config.pattern?.mode);
  const lanyardDepth = s.lanyard_depth ?? 0.65;
  const gripDepth = s.grip_rib_depth ?? 0.35;
  // ports without their own chamfer: z_offset + height/2 + 1.04 * chamfer <= T/2 + o + lip - 1.2
  const rimRoom = Math.min(
    Infinity,
    ...(config.ports || [])
      .filter((p) => p.chamfer === null || p.chamfer === undefined)
      .map((p) => (T / 2 + o + s.front_lip_thickness - 1.2 - (p.z_offset || 0) - p.height / 2) / PORT_FLARE_RISE)
  );
  return {
    // front lip: thickness >= o + lip + 0.6; ports: height/2 + |z| <= T/2 + o
    frame_to_phone_offset: range(0.05, portNeed, 0.6, s.front_lip_thickness - s.front_lip - MIN_FLOOR, 0.01),
    // snap_engage > sc + 0.2; rear lip bp_t - tongue - sc >= 0.6; button pocket fits the wall
    backplate_snap_clearance: range(
      0.05,
      -Infinity,
      0.35,
      Math.min(s.snap_engage - 0.2, s.backplate_thickness - s.tongue_height - MIN_FLOOR, T / 2 - flangeHalf - c.button_clearance),
      0.01
    ),
    button_clearance: range(0.05, -Infinity, 0.45, T / 2 - sc - flangeHalf, 0.01),
    camera_ring_clearance: [0.05, 0.35],
    // groove <= 60 % of the wall, >= 0.6 mm TPU behind it and around the button pocket
    // ... and >= 0.6 mm behind the grip grooves
    frame_wall: range(
      1.4,
      Math.max(
        s.groove_depth / 0.6,
        s.groove_depth + MIN_FLOOR,
        s.button_flange_thickness + s.button_travel + MIN_FLOOR,
        s.grip_ribs ? gripDepth + MIN_FLOOR : 0
      ),
      2.4,
      Infinity,
      0.05
    ),
    front_lip: range(0.6, -Infinity, 2.0, s.front_lip_thickness - o - MIN_FLOOR, 0.05),
    // tongue leaves >= 0.6 mm plate body and rear lip; MagSafe floor; deboss/inlay floor
    backplate_thickness: range(
      1.6,
      Math.max(
        s.tongue_height + MIN_FLOOR,
        s.tongue_height + sc + MIN_FLOOR,
        s.magsafe_ring ? s.magsafe_depth + 0.7 : 0,
        s.lanyard_pocket ? lanyardDepth + MIN_FLOOR : 0,
        recess ? (config.pattern.depth || 0) + MIN_FLOOR : 0
      ),
      2.0,
      Infinity,
      0.05
    ),
    // ergonomics (style.port_chamfer / grip_rib_depth / lanyard_depth in params.py)
    port_chamfer: range(0, -Infinity, 1.2, rimRoom, 0.05),
    grip_rib_depth: range(0.2, -Infinity, 0.6, s.frame_wall - MIN_FLOOR, 0.05),
    lanyard_depth: range(0.4, -Infinity, 0.9, s.backplate_thickness - MIN_FLOOR, 0.05),
    // snap_engage < groove <= min(60 % of the wall, wall - 0.6)
    groove_depth: range(0.6, s.snap_engage + STEP_EPS - FP, 1.2, Math.min(0.6 * s.frame_wall, s.frame_wall - MIN_FLOOR), 0.05),
    snap_engage: range(0.4, sc + 0.2 + STEP_EPS - FP, 0.85, s.groove_depth - STEP_EPS + FP, 0.05),
  };
}
