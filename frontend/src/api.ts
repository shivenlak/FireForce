import type {
  AOIRequest, CalendarResponse, Health, PointsResponse, RecentResponse, Region,
  SummaryResponse, ValidationResponse,
} from "./types";

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* not json */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown, signal?: AbortSignal) =>
  fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).then(handle<T>);

export const api = {
  health: () => fetch("/api/health").then(handle<Health>),
  regions: () => fetch("/api/regions").then(handle<Region[]>),
  regionGeometry: (name: string) =>
    fetch(`/api/regions/${encodeURIComponent(name)}/geometry`).then(handle<GeoJSON.Feature>),
  calendar: (req: AOIRequest, s?: AbortSignal) => post<CalendarResponse>("/api/calendar", req, s),
  summary: (req: AOIRequest, s?: AbortSignal) => post<SummaryResponse>("/api/summary", req, s),
  points: (req: AOIRequest, s?: AbortSignal) => post<PointsResponse>("/api/points", req, s),
  validation: () => fetch("/api/validation").then(handle<ValidationResponse>),
  methods: () => fetch("/api/methods").then((r) => r.text()),
  recent: (bbox: number[], days = 7) =>
    fetch(`/api/recent?bbox=${bbox.map((v) => v.toFixed(3)).join(",")}&days=${days}`).then(handle<RecentResponse>),
};

/** POST a request and save the CSV response as a file. */
export async function downloadCsv(path: string, req: AOIRequest, filename: string) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(`Download failed: ${r.status}`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
