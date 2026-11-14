import { useCallback, useEffect, useMemo, useState } from "react";
import type { AOI, ViewState } from "./aoi";
import { aoiBbox, aoiGeometry, aoiLabel, monthEnd, monthStart, readUrl, writeUrl } from "./aoi";
import { api, downloadCsv } from "./api";
import { AnnualChart, Cards, ClimatologyChart } from "./components/Analytics";
import Calendar from "./components/Calendar";
import MapView from "./components/MapView";
import Methods from "./components/Methods";
import Sidebar from "./components/Sidebar";
import type { AOIRequest, CalendarResponse, Health, PointsResponse, RecentResponse, Region, SummaryResponse } from "./types";

const DEFAULT_BBOX: [number, number, number, number] = [-121.5, 49, -118.5, 52];

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const f = () => setHash(window.location.hash);
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return hash.startsWith("#/methods") ? "methods" : "app";
}

export default function App() {
  const route = useHashRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setFatal(`Cannot reach the FireCal API (${e.message}). Is the backend running? Try "make dev".`));
    api.regions().then(setRegions).catch(() => undefined);
  }, []);

  return (
    <div className="app">
      <a href="#main" className="skip">Skip to content</a>
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true">▦</span>
          <div>
            <h1>FireCal</h1>
            <p>Harmonized MODIS + VIIRS burning activity calendar</p>
          </div>
        </div>
        <nav aria-label="Pages">
          <a href="#/" aria-current={route === "app" ? "page" : undefined}>Calendar</a>
          <a href="#/methods" aria-current={route === "methods" ? "page" : undefined}>Methods &amp; Validation</a>
        </nav>
      </header>
      {fatal && <p className="error banner" role="alert">{fatal}</p>}
      {route === "methods" ? <Methods /> : health && <Explorer health={health} regions={regions} />}
    </div>
  );
}

function Explorer({ health, regions }: { health: Health; regions: Region[] }) {
  const endYm = health.data_end.slice(0, 7);
  const [view, setViewState] = useState<ViewState>(() =>
    readUrl({
      aoi: { kind: "bbox", bbox: health.default_bbox ?? DEFAULT_BBOX },
      start: "2000-11",
      end: endYm,
      mode: "harmonized",
      color: "counts",
      numbers: false,
    }),
  );
  const setView = useCallback((p: Partial<ViewState>) => setViewState((v) => ({ ...v, ...p })), []);
  useEffect(() => writeUrl(view), [view]);

  const [cal, setCal] = useState<CalendarResponse | null>(null);
  const [sum, setSum] = useState<SummaryResponse | null>(null);
  const [pts, setPts] = useState<PointsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countryFeature, setCountryFeature] = useState<GeoJSON.Feature | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [recent, setRecent] = useState<RecentResponse | null>(null);
  const [liveStatus, setLiveStatus] = useState<string | null>(null);

  const req: AOIRequest = useMemo(() => ({
    aoi: aoiGeometry(view.aoi),
    country: view.aoi.kind === "country" ? view.aoi.name : null,
    start: monthStart(view.start),
    end: monthEnd(view.end),
    mode: view.mode,
  }), [view.aoi, view.start, view.end, view.mode]);

  const countryBbox = view.aoi.kind === "country" ? regions.find((r) => r.name === (view.aoi as { name: string }).name)?.bbox : undefined;
  const bbox = aoiBbox(view.aoi, countryBbox);

  useEffect(() => {
    if (view.aoi.kind !== "country") { setCountryFeature(null); return; }
    api.regionGeometry(view.aoi.name).then(setCountryFeature).catch(() => setCountryFeature(null));
  }, [view.aoi]);

  useEffect(() => {
    const ctl = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([api.calendar({ ...req }, ctl.signal), api.summary(req, ctl.signal), api.points(req, ctl.signal)])
      .then(([c, s, p]) => { setCal(c); setSum(s); setPts(p); })
      .catch((e) => { if (e.name !== "AbortError") setError(e.message); })
      .finally(() => { if (!ctl.signal.aborted) setLoading(false); });
    return () => ctl.abort();
  }, [req]);

  useEffect(() => {
    if (!live || !bbox) { setRecent(null); setLiveStatus(null); return; }
    setLiveStatus("Fetching last 7 days from FIRMS…");
    api.recent(bbox, 7).then((r) => {
      setRecent(r);
      setLiveStatus(r.error ?? `${r.points.length.toLocaleString()} live detections (NOAA-20/21 + MODIS NRT), fetched ${r.fetched_at.slice(11, 16)} UTC`);
    }).catch((e) => setLiveStatus(`Live layer failed: ${e.message}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, bbox?.join(",")]);

  const onDraw = useCallback((a: AOI) => setView({ aoi: a }), [setView]);
  const onDownload = async (kind: "hotspots" | "calendar") => {
    setDownloading(kind);
    try {
      if (kind === "hotspots") await downloadCsv("/api/hotspots.csv", req, "firecal_hotspots.csv");
      else await downloadCsv("/api/calendar.csv", req, "firecal_calendar.csv");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloading(null);
    }
  };

  const empty = cal && cal.cells.every((c) => !c.value);
  return (
    <div className="layout">
      <Sidebar view={view} regions={regions} health={health} setView={setView} onDownload={onDownload}
        downloading={downloading} live={live} setLive={setLive} liveStatus={liveStatus} />
      <main id="main" className="content">
        <div className="maprow">
          <MapView aoi={view.aoi} bbox={bbox} countryFeature={countryFeature} points={pts} recent={recent} onDraw={onDraw} />
        </div>
        {error && <p className="error" role="alert">Something went wrong: {error}</p>}
        <section className="panel calendar-panel" aria-labelledby="cal-h" aria-busy={loading}>
          <div className="panel-head">
            <div>
              <h2 id="cal-h">Burning activity calendar</h2>
              <p className="muted small">
                {aoiLabel(view.aoi)} · {cal?.units ?? ""} · baseline {cal?.baseline_years.join("–") ?? "—"} · data through {health.data_end}
              </p>
            </div>
            {loading && <span className="spinner" role="status">Loading…</span>}
          </div>
          {cal && !empty && <Calendar data={cal} color={view.color} numbers={view.numbers} />}
          {empty && !loading && (
            <p className="empty">No hotspots in this area for the selected dates. Try a larger area or a different country{health.sample ? " (the sample dataset only covers the Kelowna–Kamloops box)" : ""}.</p>
          )}
          {!cal && loading && <div className="skeleton" style={{ height: 520 }} />}
        </section>
        {sum && !empty && (
          <>
            <Cards s={sum} currentFlags={cal?.cells.find((c) => sum.current && c.year === sum.current.year && c.month === sum.current.month)?.flags ?? []} />
            <div className="grid2">
              <section className="panel"><AnnualChart s={sum} /></section>
              <section className="panel"><ClimatologyChart s={sum} /></section>
            </div>
          </>
        )}
        <footer className="foot muted small">
          Data: NASA FIRMS (MODIS C6.1 / VIIRS S-NPP 375 m, standard + NRT). Units are fire cell-days on a{" "}
          common grid; see <a href="#/methods">Methods</a>. Not for operational decisions without checking local sources.
        </footer>
      </main>
    </div>
  );
}
