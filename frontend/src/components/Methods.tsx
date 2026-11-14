import ReactECharts from "echarts-for-react";
import { marked } from "marked";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { SERIES, fmt } from "../colors";
import type { CountryValidation, Metrics, ValidationResponse } from "../types";

const pctf = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v.toFixed(1)}%`);
const r2f = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toFixed(3));

export default function Methods() {
  const [val, setVal] = useState<ValidationResponse | null>(null);
  const [md, setMd] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [country, setCountry] = useState<string>("");
  const [unit, setUnit] = useState<"celldays" | "detections">("celldays");

  useEffect(() => {
    api.validation().then((v) => {
      setVal(v);
      setCountry(Object.keys(v.validation)[0] ?? "");
    }).catch((e) => setErr(String(e)));
    api.methods().then(setMd).catch(() => setMd(""));
  }, []);

  const v: CountryValidation | undefined = val?.validation[country];
  const html = useMemo(() => (md ? (marked.parse(md) as string) : ""), [md]);

  if (err) return <main className="methods"><p className="error" role="alert">Could not load validation: {err}</p></main>;
  if (!val) return <main className="methods"><p className="loading">Loading validation…</p></main>;
  if (!v) return <main className="methods"><p>No validation results yet. Run <code>make data</code>.</p></main>;

  return (
    <main className="methods" id="main">
      <header className="methods-head">
        <h1>Methods &amp; Validation</h1>
        <label>
          Country{" "}
          <select value={country} onChange={(e) => setCountry(e.target.value)}>
            {Object.keys(val.validation).map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
          </select>
        </label>
      </header>

      <section className="kpis" aria-label="Headline validation metrics">
        <Kpi label="Leave-one-year-out R² (monthly)" value={r2f(v.loyo.r2)} />
        <Kpi label="Monthly MAPE" value={pctf(v.loyo.mape)} />
        <Kpi label="Bias" value={pctf(v.loyo.bias_pct)} />
        <Kpi label="Annual-total R²" value={r2f(v.loyo.annual_r2)} />
        <Kpi label="Grid · model" value={`${v.grid_deg}° · ${v.method}`} />
        <Kpi label="Overlap window" value={`${v.overlap[0]} → ${v.overlap[1]}`} />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Raw sensors disagree; harmonized series overlap</h2>
          <div className="seg small" role="radiogroup" aria-label="Units">
            <button role="radio" aria-checked={unit === "celldays"} className={unit === "celldays" ? "on" : ""} onClick={() => setUnit("celldays")}>Cell-days</button>
            <button role="radio" aria-checked={unit === "detections"} className={unit === "detections" ? "on" : ""} onClick={() => setUnit("detections")}>Raw detections</button>
          </div>
        </div>
        <OverlapChart v={v} unit={unit} />
        <p className="muted small">
          Monthly totals for {country.replace(/_/g, " ")} during the overlap. Blue = MODIS (the reference), orange = VIIRS as observed,
          green = VIIRS after calibration (MODIS-equivalent). A good harmonization puts green on top of blue.
        </p>
      </section>

      <section className="panel">
        <h2>Full harmonized record</h2>
        <FullSeries v={v} />
      </section>

      <section className="grid2">
        <div className="panel">
          <h2>Skill comparison</h2>
          <table className="tbl">
            <thead><tr><th>Test</th><th>R²</th><th>MAPE</th><th>Bias</th><th>Annual R²</th></tr></thead>
            <tbody>
              <Row name={<b>Chosen model, LOYO</b>} m={v.loyo} />
              <Row name="Same, on raw detections (no cell-days)" m={v.raw_detection_baseline.loyo} />
              <Row name="Overlap ending 2022 (sensitivity)" m={v.sensitivity_overlap_2022} />
              <Row name="Forward: fit 2012–19, predict 2020–25" m={v.forward_test_2020_2025} />
            </tbody>
          </table>
          <p className="muted small">
            Year-to-year variability (CV) of the VIIRS/MODIS ratio: <b>{v.raw_detection_baseline.celldays_annual_ratio_cv.toFixed(2)}</b> with
            cell-days vs {v.raw_detection_baseline.annual_ratio_cv.toFixed(2)} with raw detections.
            Weight invariant (Σ harmonized_weight = series): max relative error {v.invariant_max_rel_err.toExponential(1)}.
          </p>
        </div>
        <div className="panel">
          <h2>Grid × model candidates (LOYO)</h2>
          <table className="tbl">
            <thead><tr><th>Grid</th><th>Model</th><th>MAPE</th><th>Bias</th><th>Annual R²</th><th>Score</th></tr></thead>
            <tbody>
              {Object.entries(v.candidates).map(([k, m]) => {
                const [g, meth] = k.split("|");
                const chosen = Number(g) === v.grid_deg && meth === v.method;
                return (
                  <tr key={k} className={chosen ? "chosen" : ""}>
                    <td>{g}°</td><td>{meth}{chosen ? " ✓" : ""}</td><td>{pctf(m.mape)}</td><td>{pctf(m.bias_pct)}</td><td>{r2f(m.annual_r2)}</td><td>{m.score?.toFixed(1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="muted small">Score = MAPE + |bias|. Bias is penalized because it distorts long-term trends.</p>
        </div>
      </section>

      <section className="grid2">
        <div className="panel">
          <h2>Calibration ratio k by month</h2>
          <KChart v={v} />
        </div>
        <div className="panel">
          <h2>Consistency checks</h2>
          <ul className="checks">
            <li><b>Aqua vs S-NPP</b> (both ~13:30 overpass): monthly correlation r = {v.aqua_vs_snpp.pearson_r_monthly}; VIIRS/Aqua cell-day ratio {v.aqua_vs_snpp.median_ratio_viirs_over_aqua}.</li>
            <li><b>Terra-only era</b> (Nov 2000 – Jun 2002): ×{v.terra_factor.pooled.toFixed(2)} pooled correction (per month {Math.min(...Object.values(v.terra_factor.months)).toFixed(2)}–{Math.max(...Object.values(v.terra_factor.months)).toFixed(2)}), estimated from 2003–2011.</li>
            <li><b>S-NPP outage months</b> (filled with calibrated NOAA-20 where available, otherwise MODIS):{" "}
              {v.outage_months.length ? v.outage_months.map((m) => `${m} (${(v.outage_fill_source?.[m] ?? "MODIS").replace("VIIRS_N20", "NOAA-20")})`).join(", ") : "none"}.</li>
            {v.noaa20 && (
              <li><b>NOAA-20 → MODIS calibration</b> ({v.noaa20.overlap.join(" → ")}): LOYO R² {r2f(v.noaa20.loyo.r2)}, MAPE {pctf(v.noaa20.loyo.mape)}, bias {pctf(v.noaa20.loyo.bias_pct)}.
                This lets the record continue on NOAA-20 when S-NPP is down, and after MODIS ends.</li>
            )}
          </ul>
          <h3>Per-year LOYO error</h3>
          <PerYear v={v} />
        </div>
      </section>

      {html && <article className="panel prose" dangerouslySetInnerHTML={{ __html: html }} />}
    </main>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return <div className="kpi"><div className="kpi-v">{value}</div><div className="kpi-l">{label}</div></div>;
}

function Row({ name, m }: { name: React.ReactNode; m: Metrics }) {
  return <tr><td>{name}</td><td>{r2f(m.r2)}</td><td>{pctf(m.mape)}</td><td>{pctf(m.bias_pct)}</td><td>{r2f(m.annual_r2)}</td></tr>;
}

function OverlapChart({ v, unit }: { v: CountryValidation; unit: "celldays" | "detections" }) {
  const rows = v.series.filter((r) => r.ym >= v.overlap[0] && r.ym <= v.overlap[1]);
  const m = unit === "celldays" ? rows.map((r) => r.M) : rows.map((r) => r.det_M);
  const vv = unit === "celldays" ? rows.map((r) => r.V) : rows.map((r) => r.det_V);
  const option = {
    animation: false,
    aria: { enabled: true },
    grid: { top: 36, bottom: 60, left: 60, right: 16 },
    legend: { top: 0 },
    tooltip: { trigger: "axis", valueFormatter: (x: number) => fmt(x, 0) },
    dataZoom: [{ type: "slider", height: 18, bottom: 8 }],
    xAxis: { type: "category", data: rows.map((r) => r.ym) },
    yAxis: { type: "log", name: unit === "celldays" ? "cell-days (log)" : "detections (log)", min: 1 },
    series: [
      { name: "MODIS", type: "line", data: m.map((x) => Math.max(x, 1)), symbol: "none", lineStyle: { width: 2.5 }, itemStyle: { color: SERIES.modis } },
      { name: "VIIRS raw", type: "line", data: vv.map((x) => Math.max(x, 1)), symbol: "none", lineStyle: { width: 1.5 }, itemStyle: { color: SERIES.viirs } },
      { name: "VIIRS harmonized", type: "line", data: rows.map((r) => Math.max(r.V_cal, 1)), symbol: "none", lineStyle: { width: 2, type: "dashed" }, itemStyle: { color: SERIES.harmonized } },
    ],
  };
  return <ReactECharts option={option} style={{ height: 320 }} />;
}

function FullSeries({ v }: { v: CountryValidation }) {
  const rows = v.series;
  const option = {
    animation: false,
    grid: { top: 30, bottom: 60, left: 60, right: 16 },
    legend: { top: 0 },
    tooltip: { trigger: "axis", valueFormatter: (x: number) => fmt(x, 0) },
    dataZoom: [{ type: "slider", height: 18, bottom: 8 }],
    xAxis: { type: "category", data: rows.map((r) => r.ym) },
    yAxis: { type: "value", name: "MODIS-eq. cell-days" },
    series: [
      { name: "Harmonized", type: "line", data: rows.map((r) => r.H), symbol: "none", lineStyle: { width: 1.8 }, itemStyle: { color: SERIES.harmonized }, areaStyle: { opacity: 0.12 } },
      { name: "MODIS (reference)", type: "line", data: rows.map((r) => r.M_adj), symbol: "none", lineStyle: { width: 1, opacity: 0.8 }, itemStyle: { color: SERIES.modis } },
    ],
    visualMap: undefined,
  };
  return (
    <>
      <ReactECharts option={option} style={{ height: 260 }} />
      <p className="muted small">The harmonized series is MODIS before Feb 2012 and calibrated VIIRS after it. MODIS is shown for comparison; after 2022 it may be affected by Terra and Aqua orbit drift.</p>
    </>
  );
}

function KChart({ v }: { v: CountryValidation }) {
  const months = Object.entries(v.coefficients.months);
  const option = {
    animation: false,
    grid: { top: 20, bottom: 30, left: 40, right: 10 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"] },
    yAxis: { type: "value", name: "k = V/M" },
    series: [{
      type: "bar",
      data: months.map(([, c]) => ({ value: c.k?.toFixed(2), itemStyle: { color: c.fallback ? SERIES.muted : SERIES.viirs } })),
    }],
  };
  return (
    <>
      <ReactECharts option={option} style={{ height: 200 }} />
      <p className="muted small">VIIRS sees k× as many fire cell-days as MODIS. k is higher in winter and spring, when fires are small (VIIRS's advantage), and lower in the main fire season. Grey = pooled fallback.</p>
    </>
  );
}

function PerYear({ v }: { v: CountryValidation }) {
  const ys = Object.entries(v.loyo_per_year);
  const option = {
    animation: false,
    grid: { top: 10, bottom: 24, left: 40, right: 10 },
    tooltip: { trigger: "axis", valueFormatter: (x: number) => `${x}%` },
    xAxis: { type: "category", data: ys.map(([y]) => y) },
    yAxis: { type: "value", name: "bias %" },
    series: [{ type: "bar", data: ys.map(([, m]) => (m.bias_pct ?? 0).toFixed(1)), itemStyle: { color: SERIES.harmonized } }],
  };
  return <ReactECharts option={option} style={{ height: 160 }} />;
}
