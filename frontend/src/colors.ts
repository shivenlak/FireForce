// Colorblind-safe ramps.
// Counts: inferno (perceptually uniform), reversed so low = pale, high = dark, on a log scale.
export const INFERNO_R = ["#fcffa4", "#f7d13d", "#fb9b06", "#ed6925", "#cf4446", "#a52c60", "#781c6d", "#4a0c6b", "#1b0c41"];
// Anomaly: RdBu diverging (ColorBrewer, colorblind-safe), blue = below normal, red = above.
export const RDBU = ["#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b"];
export const ZERO = "#ececec";
export const NODATA = "#ffffff";

// Series colors (Okabe-Ito, colorblind-safe)
export const SERIES = {
  modis: "#0072B2",
  viirs: "#E69F00",
  harmonized: "#009E73",
  current: "#D55E00",
  muted: "#999999",
};

export function interp(ramp: string[], t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (ramp.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  if (i >= ramp.length - 1) return ramp[ramp.length - 1];
  const a = hex(ramp[i]);
  const b = hex(ramp[i + 1]);
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function hex(h: string): number[] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Readable text color on a given background. */
export function textOn(bg: string): string {
  const m = bg.match(/\d+/g);
  const [r, g, b] = m && bg.startsWith("rgb") ? m.map(Number) : hex(bg);
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#111" : "#fff";
}

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function fmt(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 10000) return `${(v / 1000).toFixed(1)}k`;
  return v.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(0)}%`;
}

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
