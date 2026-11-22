// Static UI data (themes, swatches, pattern cards, calibration presets).
// Moved verbatim from App.jsx.
export const SAMPLE_SVGS = {
  star: {
    label: "Star Emblem",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M50 5 L61 38 L95 38 L67 58 L78 92 L50 71 L22 92 L33 58 L5 38 L39 38 Z"/><circle cx="50" cy="50" r="8"/></svg>',
  },
  bolt: {
    label: "Lightning Bolt",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M58 4 L18 55 L46 55 L38 96 L82 42 L53 42 Z"/></svg>',
  },
  crest: {
    label: "Geometric Crest",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M50 6 L88 28 L88 72 L50 94 L12 72 L12 28 Z M50 22 L73 35 L73 65 L50 78 L27 65 L27 35 Z"/></svg>',
  },
};

export const FILAMENT_THEMES = [
  {
    id: "bambu-orange",
    name: "Bambu Carbon",
    subtitle: "Charcoal TPU + Orange Accents",
    colors: {
      frame: "#181b20",
      backplate: "#2d333b",
      inlay: "#f97316",
      camera_ring: "#f97316",
      buttons: "#f97316",
    },
  },
  {
    id: "cyber-cyan",
    name: "Cyber Cyan",
    subtitle: "Midnight Navy + Neon Cyan",
    colors: {
      frame: "#0f172a",
      backplate: "#1e293b",
      inlay: "#06b6d4",
      camera_ring: "#22d3ee",
      buttons: "#22d3ee",
    },
  },
  {
    id: "stealth-matte",
    name: "Stealth Matte",
    subtitle: "Triple Black + Slate Ring",
    colors: {
      frame: "#111315",
      backplate: "#1c1f24",
      inlay: "#475569",
      camera_ring: "#3f444e",
      buttons: "#64748b",
    },
  },
  {
    id: "voron-racing",
    name: "Voron Racing",
    subtitle: "Jet Black + Crimson ABS",
    colors: {
      frame: "#141417",
      backplate: "#232329",
      inlay: "#ef4444",
      camera_ring: "#ef4444",
      buttons: "#ef4444",
    },
  },
  {
    id: "arctic-frost",
    name: "Arctic Frost",
    subtitle: "Storm Slate + Jade White",
    colors: {
      frame: "#334155",
      backplate: "#e2e8f0",
      inlay: "#38bdf8",
      camera_ring: "#0284c7",
      buttons: "#38bdf8",
    },
  },
  {
    id: "walnut-gold",
    name: "Walnut & Brass",
    subtitle: "Laser Wood + Silk Gold",
    colors: {
      frame: "#1c1917",
      backplate: "#78350f",
      inlay: "#eab308",
      camera_ring: "#eab308",
      buttons: "#eab308",
    },
  },
];

export const BAMBU_SWATCHES = [
  { name: "Matte Charcoal", hex: "#1e293b" },
  { name: "Bambu Cyan", hex: "#06b6d4" },
  { name: "Bambu Orange", hex: "#f97316" },
  { name: "Jade White", hex: "#e2e8f0" },
  { name: "Crimson Red", hex: "#ef4444" },
  { name: "Bambu Green", hex: "#10b981" },
  { name: "Royal Indigo", hex: "#6366f1" },
  { name: "Gold Silk", hex: "#eab308" },
  { name: "Walnut Wood", hex: "#78350f" },
];

// Fallback icons for the pattern gallery (shown until, or instead of, the live thumbnail).
const icon = (children) => (
  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    {children}
  </svg>
);
export const PATTERN_ICONS = {
  solid: icon(<rect x="5" y="2" width="14" height="20" rx="3" />),
  hex: icon(
    <>
      <path d="M12 2l5.2 3v6L12 14l-5.2-3V5L12 2z" />
      <path d="M6.8 11l5.2 3v6l-5.2 3-5.2-3v-6l5.2-3z" />
      <path d="M17.2 11l5.2 3v6l-5.2 3-5.2-3v-6l5.2-3z" />
    </>
  ),
  dots: icon(
    <>
      <circle cx="7" cy="7" r="2.5" />
      <circle cx="17" cy="7" r="2.5" />
      <circle cx="12" cy="16" r="2.5" />
    </>
  ),
  triangles: icon(<path d="M12 3l9 16H3L12 3zM7.5 11h9M12 19l-4.5-8M12 19l4.5-8" />),
  grid: icon(
    <>
      <path d="M12 2l8 10-8 10L4 12 12 2z" />
      <path d="M8 7l8 10M16 7L8 17" />
    </>
  ),
  voronoi: icon(
    <>
      <polygon points="4,4 13,3 11,11 3,12" />
      <polygon points="13,3 21,6 19,15 11,11" />
      <polygon points="3,12 11,11 13,20 5,21" />
      <polygon points="11,11 19,15 20,21 13,20" />
    </>
  ),
  waves: icon(
    <>
      <path d="M2 8c3-4 6-4 9 0s6 4 11 0" />
      <path d="M2 14c3-4 6-4 9 0s6 4 11 0" />
      <path d="M2 20c3-4 6-4 9 0s6 4 11 0" />
    </>
  ),
  chevron: icon(<path d="M2 9l5-5 5 5 5-5 5 5M2 16l5-5 5 5 5-5 5 5" />),
  text: icon(<path d="M4 7V4h16v3M9 20h6M12 4v16" />),
  svg: icon(
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  ),
};

export const CALIBRATION_PROFILES = [
  {
    id: "h3c",
    label: "H3C / Tool-Changer",
    desc: "Co-printed multi-head tolerances",
    clearances: {
      frame_to_phone_offset: 0.25,
      backplate_snap_clearance: 0.15,
      button_clearance: 0.2,
      camera_ring_clearance: 0.15,
    },
  },
  {
    id: "bambu_68d",
    label: "Bambu AMS (68D)",
    desc: "Rigid TPU 68D snap-fit clearances",
    clearances: {
      frame_to_phone_offset: 0.25,
      backplate_snap_clearance: 0.15,
      button_clearance: 0.2,
      camera_ring_clearance: 0.15,
    },
  },
  {
    id: "soft_95a",
    label: "Soft TPU 95A",
    desc: "Tighter snap grip for flexible 95A",
    clearances: {
      frame_to_phone_offset: 0.15,
      backplate_snap_clearance: 0.12,
      button_clearance: 0.22,
      camera_ring_clearance: 0.15,
    },
  },
];

export const FINISH_MODES = [
  { id: "through", label: "Through-cut", desc: "Open holes. Also exports a laser-cut outline." },
  { id: "deboss", label: "Deboss", desc: "Recessed into the back face." },
  { id: "inlay", label: "Inlay", desc: "A second colour, flush with the back (multi-material 3MF)." },
];

export const DEFAULT_VISIBLE = {
  frame: true,
  backplate: true,
  inlay: true,
  camera_ring: true,
  buttons: true,
};

export function cleanDeviceName(name = "") {
  return name.replace(" (approx - verify with calipers)", "");
}
