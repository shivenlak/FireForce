import type { Geometry, Mode } from "./types";

/** An area of interest, serializable to the URL query string. */
export type AOI =
  | { kind: "bbox"; bbox: [number, number, number, number] }
  | { kind: "circle"; lat: number; lon: number; km: number }
  | { kind: "polygon"; ring: [number, number][] } // [lon, lat]
  | { kind: "country"; name: string };

export interface ViewState {
  aoi: AOI;
  start: string; // YYYY-MM
  end: string;
  mode: Mode;
  color: "counts" | "anomaly";
  numbers: boolean;
}

export function aoiGeometry(a: AOI): Geometry | null {
  switch (a.kind) {
    case "bbox": {
      const [w, s, e, n] = a.bbox;
      return { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
    }
    case "circle":
      return { type: "Polygon", coordinates: [circleRing(a.lat, a.lon, a.km)] };
    case "polygon":
      return { type: "Polygon", coordinates: [[...a.ring, a.ring[0]]] };
    case "country":
      return null;
  }
}

export function circleRing(lat: number, lon: number, km: number, n = 64): [number, number][] {
  const ring: [number, number][] = [];
  const dLat = km / 110.574;
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= n; i++) {
    const t = (2 * Math.PI * i) / n;
    ring.push([+(lon + dLon * Math.cos(t)).toFixed(5), +(lat + dLat * Math.sin(t)).toFixed(5)]);
  }
  return ring;
}

export function aoiBbox(a: AOI, countryBbox?: number[]): [number, number, number, number] | null {
  if (a.kind === "country") return (countryBbox as [number, number, number, number]) ?? null;
  const g = aoiGeometry(a)!;
  const ring = (g.coordinates as number[][][])[0];
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export function aoiLabel(a: AOI): string {
  switch (a.kind) {
    case "bbox":
      return `Box ${a.bbox.map((v) => v.toFixed(2)).join(", ")}`;
    case "circle":
      return `${a.km} km around ${a.lat.toFixed(3)}, ${a.lon.toFixed(3)}`;
    case "polygon":
      return `Polygon (${a.ring.length} vertices)`;
    case "country":
      return a.name.replace(/_/g, " ");
  }
}

// ---------- URL state
export function encodeAoi(a: AOI): string {
  switch (a.kind) {
    case "bbox":
      return `bbox:${a.bbox.map((v) => +v.toFixed(4)).join(",")}`;
    case "circle":
      return `circle:${a.lat.toFixed(4)},${a.lon.toFixed(4)},${a.km}`;
    case "polygon":
      return `poly:${a.ring.map(([x, y]) => `${x.toFixed(4)} ${y.toFixed(4)}`).join(";")}`;
    case "country":
      return `country:${a.name}`;
  }
}

export function decodeAoi(s: string | null): AOI | null {
  if (!s) return null;
  const [kind, rest] = [s.slice(0, s.indexOf(":")), s.slice(s.indexOf(":") + 1)];
  const nums = rest.split(",").map(Number);
  if (kind === "bbox" && nums.length === 4 && nums.every(Number.isFinite))
    return { kind: "bbox", bbox: nums as [number, number, number, number] };
  if (kind === "circle" && nums.length === 3 && nums.every(Number.isFinite))
    return { kind: "circle", lat: nums[0], lon: nums[1], km: nums[2] };
  if (kind === "poly") {
    const ring = rest.split(";").map((p) => p.split(" ").map(Number) as [number, number]);
    if (ring.length >= 3 && ring.every((p) => p.length === 2 && p.every(Number.isFinite)))
      return { kind: "polygon", ring };
  }
  if (kind === "country" && rest) return { kind: "country", name: rest };
  return null;
}

export function readUrl(defaults: ViewState): ViewState {
  const q = new URLSearchParams(window.location.search);
  const mode = q.get("mode");
  return {
    aoi: decodeAoi(q.get("aoi")) ?? defaults.aoi,
    start: q.get("start") ?? defaults.start,
    end: q.get("end") ?? defaults.end,
    mode: mode === "modis" || mode === "viirs" || mode === "harmonized" ? mode : defaults.mode,
    color: q.get("color") === "anomaly" ? "anomaly" : defaults.color,
    numbers: q.get("numbers") === "1" || defaults.numbers,
  };
}

export function writeUrl(v: ViewState) {
  const q = new URLSearchParams(window.location.search);
  q.set("aoi", encodeAoi(v.aoi));
  q.set("start", v.start);
  q.set("end", v.end);
  q.set("mode", v.mode);
  q.set("color", v.color);
  if (v.numbers) q.set("numbers", "1");
  else q.delete("numbers");
  const url = `${window.location.pathname}?${q.toString()}${window.location.hash}`;
  window.history.replaceState(null, "", url);
}

export function monthStart(ym: string): string {
  return `${ym}-01`;
}

export function monthEnd(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return `${ym}-${String(d).padStart(2, "0")}`;
}
