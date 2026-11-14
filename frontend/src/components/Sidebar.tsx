import { useState } from "react";
import type { AOI, ViewState } from "../aoi";
import { aoiLabel } from "../aoi";
import type { Health, Mode, Region } from "../types";

interface Props {
  view: ViewState;
  regions: Region[];
  health: Health | null;
  setView: (v: Partial<ViewState>) => void;
  onDownload: (kind: "hotspots" | "calendar") => void;
  downloading: string | null;
  live: boolean;
  setLive: (b: boolean) => void;
  liveStatus: string | null;
}

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "harmonized", label: "Harmonized", hint: "MODIS-equivalent units, 2000–today" },
  { id: "modis", label: "Raw MODIS", hint: "Uncalibrated MODIS cell-days" },
  { id: "viirs", label: "Raw VIIRS", hint: "Uncalibrated S-NPP cell-days, 2012–" },
];

export default function Sidebar(p: Props) {
  const { view, setView } = p;
  const [lat, setLat] = useState("50.5");
  const [lon, setLon] = useState("-120.0");
  const [km, setKm] = useState("100");
  const [err, setErr] = useState<string | null>(null);

  const applyCircle = (e: React.FormEvent) => {
    e.preventDefault();
    const a = Number(lat), o = Number(lon), r = Number(km);
    if (!(Math.abs(a) <= 90 && Math.abs(o) <= 180 && r > 0 && r <= 2000)) {
      setErr("Enter latitude −90…90, longitude −180…180 and a radius of 1–2000 km.");
      return;
    }
    setErr(null);
    setView({ aoi: { kind: "circle", lat: a, lon: o, km: r } });
  };
  const setAoi = (aoi: AOI) => setView({ aoi });

  return (
    <aside className="sidebar" aria-label="Controls">
      <fieldset>
        <legend>1 · Area</legend>
        <p className="current-aoi" aria-live="polite"><b>Selected:</b> {aoiLabel(view.aoi)}</p>
        <p className="muted small">Draw a rectangle or polygon with the tools on the map, or:</p>
        <label htmlFor="country">Country</label>
        <select
          id="country"
          value={view.aoi.kind === "country" ? view.aoi.name : ""}
          onChange={(e) => e.target.value && setAoi({ kind: "country", name: e.target.value })}
        >
          <option value="">Choose a country…</option>
          {p.regions.map((r) => (
            <option key={r.name} value={r.name} disabled={!r.has_data}>
              {r.label}{r.has_data ? "" : " (not processed yet)"}
            </option>
          ))}
        </select>
        <form className="circle-form" onSubmit={applyCircle}>
          <div className="row3">
            <label>Lat<input inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} aria-label="Latitude" /></label>
            <label>Lon<input inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} aria-label="Longitude" /></label>
            <label>km<input inputMode="decimal" value={km} onChange={(e) => setKm(e.target.value)} aria-label="Radius in kilometres" /></label>
          </div>
          <button type="submit">Use point + radius</button>
          {err && <p className="error" role="alert">{err}</p>}
        </form>
        {p.health && (
          <button className="link" onClick={() => setAoi({ kind: "bbox", bbox: p.health!.default_bbox })}>
            Reset to {p.health.default_label}
          </button>
        )}
      </fieldset>

      <fieldset>
        <legend>2 · Dates</legend>
        <div className="row2">
          <label>From<input type="month" value={view.start} min="2000-11" max={view.end} onChange={(e) => e.target.value && setView({ start: e.target.value })} /></label>
          <label>To<input type="month" value={view.end} min={view.start} onChange={(e) => e.target.value && setView({ end: e.target.value })} /></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>3 · Series</legend>
        <div className="seg" role="radiogroup" aria-label="Sensor mode">
          {MODES.map((m) => (
            <button key={m.id} role="radio" aria-checked={view.mode === m.id} className={view.mode === m.id ? "on" : ""} title={m.hint} onClick={() => setView({ mode: m.id })}>
              {m.label}
            </button>
          ))}
        </div>
        <p className="muted small">{MODES.find((m) => m.id === view.mode)?.hint}</p>
        <div className="seg" role="radiogroup" aria-label="Calendar colors">
          <button role="radio" aria-checked={view.color === "counts"} className={view.color === "counts" ? "on" : ""} onClick={() => setView({ color: "counts" })}>Counts</button>
          <button role="radio" aria-checked={view.color === "anomaly"} className={view.color === "anomaly" ? "on" : ""} onClick={() => setView({ color: "anomaly" })}>Anomaly</button>
        </div>
        <label className="check"><input type="checkbox" checked={view.numbers} onChange={(e) => setView({ numbers: e.target.checked })} /> Print numbers in cells</label>
        <label className="check"><input type="checkbox" checked={p.live} onChange={(e) => p.setLive(e.target.checked)} /> Live: last 7 days (NRT)</label>
        {p.liveStatus && <p className="muted small" aria-live="polite">{p.liveStatus}</p>}
      </fieldset>

      <fieldset>
        <legend>4 · Download</legend>
        <button onClick={() => p.onDownload("calendar")} disabled={!!p.downloading}>
          {p.downloading === "calendar" ? "Preparing…" : "Calendar table (CSV)"}
        </button>
        <button onClick={() => p.onDownload("hotspots")} disabled={!!p.downloading}>
          {p.downloading === "hotspots" ? "Preparing…" : "Hotspots + weights (CSV)"}
        </button>
        <p className="muted small">Hotspot export covers the selected dates (max 500,000 rows). Summing <code>harmonized_weight</code> reproduces the calendar.</p>
      </fieldset>
      {p.health?.sample && (
        <p className="notice">Showing the small sample dataset ({p.health.default_label}). Run <code>make data</code> for full countries.</p>
      )}
    </aside>
  );
}
