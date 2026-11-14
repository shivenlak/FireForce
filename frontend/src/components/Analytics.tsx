import ReactECharts from "echarts-for-react";
import { MONTHS, SERIES, fmt, ordinal, pct } from "../colors";
import type { SummaryResponse } from "../types";

const SENSORS: [string, string, string][] = [
  ["MODIS", "MODIS", SERIES.modis], ["VIIRS", "S-NPP", SERIES.viirs], ["VIIRS_N20", "NOAA-20", SERIES.n20],
];

export function Cards({ s, currentFlags = [] }: { s: SummaryResponse; currentFlags?: string[] }) {
  const c = s.current;
  const share = s.sensor_share.harmonized;
  return (
    <div className="cards">
      <section className="card" aria-labelledby="c-now">
        <h3 id="c-now">This month vs. history</h3>
        {c ? (
          <>
            <p className="big">
              {fmt(c.value, 0)}
              <span className={`delta ${c.anomaly_pct !== null && c.anomaly_pct > 0 ? "up" : "down"}`}>
                {pct(c.anomaly_pct)}
              </span>
            </p>
            <p>
              {MONTHS[c.month - 1]} 1–{c.day}, {c.year}: <b>{ordinal(c.rank)} highest</b> of {c.n_years} years
              {c.percentile !== null && <> ({c.percentile.toFixed(0)}th percentile)</>}.
            </p>
            <p className="muted">
              Compared with the same days ({MONTHS[c.month - 1]} 1–{c.day}) in every year. Median {fmt(c.median, 0)}.
            </p>
            {currentFlags.includes("gap_filled") && (
              <p className="flagnote">⚑ VIIRS S-NPP data are missing for part of this month, so this value comes from a backup sensor (calibrated NOAA-20 or MODIS; same MODIS-equivalent units).</p>
            )}
            <MiniHistory s={s} />
          </>
        ) : <p className="muted">No current-month data for this area.</p>}
      </section>
      <section className="card" aria-labelledby="c-pm">
        <h3 id="c-pm">Peak fire months</h3>
        <ol className="rank">
          {s.peak_months.map((m) => (
            <li key={`${m.year}-${m.month}`}><span>{MONTHS[m.month - 1]} {m.year}</span><b>{fmt(m.value)}</b></li>
          ))}
        </ol>
        <h3 id="c-py">Biggest fire years</h3>
        <ol className="rank">
          {s.peak_years.map((y) => (
            <li key={y.year}><span>{y.year}</span><b>{fmt(y.value)}</b></li>
          ))}
        </ol>
      </section>
      <section className="card" aria-labelledby="c-src">
        <h3 id="c-src">Where the numbers come from</h3>
        <div className="sharebar" role="img" aria-label={SENSORS.map(([k, l]) => `${l} ${((share[k] ?? 0) * 100).toFixed(0)} percent`).join(", ") + " of the harmonized total"}>
          {SENSORS.map(([k, , c]) => <span key={k} style={{ width: `${(share[k] ?? 0) * 100}%`, background: c }} />)}
        </div>
        <p>
          {SENSORS.filter(([k]) => (share[k] ?? 0) > 0).map(([k, l, c]) => (
            <span key={k} className="sharekey"><i className="dot" style={{ background: c }} /> {l} {((share[k] ?? 0) * 100).toFixed(0)}%</span>
          ))}
          <span className="muted"> of the harmonized total</span>
        </p>
        <p className="muted">
          Raw detections: {SENSORS.filter(([k]) => s.sensor_share.detections[k]).map(([k, l]) => `${l} ${s.sensor_share.detections[k].toLocaleString()}`).join(" · ")}.
          Total {fmt(s.total)} {s.units}.
        </p>
      </section>
    </div>
  );
}

function MiniHistory({ s }: { s: SummaryResponse }) {
  const c = s.current!;
  const option = {
    animation: false,
    grid: { top: 6, bottom: 18, left: 4, right: 4 },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => fmt(v, 0) },
    xAxis: { type: "category", data: c.history.map((h) => h.year), axisLabel: { fontSize: 9, interval: 4 }, axisTick: { show: false } },
    yAxis: { type: "value", show: false },
    series: [{
      type: "bar",
      data: c.history.map((h) => ({ value: h.value, itemStyle: { color: h.year === c.year ? SERIES.current : "#c9c9c9" } })),
      markLine: c.median !== null ? { symbol: "none", silent: true, data: [{ yAxis: c.median }], lineStyle: { color: "#333", type: "dashed" }, label: { show: false } } : undefined,
    }],
  };
  return <ReactECharts option={option} style={{ height: 70 }} aria-label="Month-to-date value in each year" />;
}

export function AnnualChart({ s }: { s: SummaryResponse }) {
  const option = {
    animation: false,
    aria: { enabled: true },
    grid: { top: 36, bottom: 30, left: 56, right: 12 },
    title: { text: "Annual totals", textStyle: { fontSize: 13 }, left: 0 },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => `${fmt(v, 0)}` },
    xAxis: { type: "category", data: s.annual.map((a) => a.year) },
    yAxis: { type: "value" },
    series: [{
      type: "bar",
      data: s.annual.map((a) => ({
        value: a.value,
        itemStyle: a.partial
          ? { color: "#fff", borderColor: SERIES.harmonized, borderWidth: 1.5, borderType: "dashed" }
          : { color: a.year < 2012 ? SERIES.modis : SERIES.harmonized },
      })),
    }],
  };
  return (
    <div className="chart">
      <ReactECharts option={option} style={{ height: 240 }} />
      <p className="muted small">
        <i className="dot" style={{ background: SERIES.modis }} /> MODIS era (2000–2011) ·{" "}
        <i className="dot" style={{ background: SERIES.harmonized }} /> calibrated VIIRS era (2012–) · dashed = partial year
      </p>
    </div>
  );
}

export function ClimatologyChart({ s }: { s: SummaryResponse }) {
  const cl = s.climatology;
  const year = s.current?.year ?? new Date().getFullYear();
  const option = {
    animation: false,
    aria: { enabled: true },
    grid: { top: 36, bottom: 30, left: 56, right: 12 },
    title: { text: "Monthly climatology", textStyle: { fontSize: 13 }, left: 0 },
    legend: { right: 0, top: 0, textStyle: { fontSize: 11 }, data: ["Median", "IQR (25–75%)", String(year)] },
    tooltip: {
      trigger: "axis",
      formatter: (p: { dataIndex: number }[]) => {
        const c = cl[p[0].dataIndex];
        return `<b>${MONTHS[c.month - 1]}</b><br/>Median ${fmt(c.median, 0)}<br/>IQR ${fmt(c.q25, 0)}–${fmt(c.q75, 0)}<br/>${year}: ${fmt(c.current, 0)}`;
      },
    },
    xAxis: { type: "category", data: MONTHS, boundaryGap: false },
    yAxis: { type: "value" },
    series: [
      { name: "q25", type: "line", data: cl.map((c) => c.q25), stack: "iqr", lineStyle: { opacity: 0 }, symbol: "none", tooltip: { show: false } },
      { name: "IQR (25–75%)", type: "line", data: cl.map((c) => (c.q75 ?? 0) - (c.q25 ?? 0)), stack: "iqr", lineStyle: { opacity: 0 }, symbol: "none", areaStyle: { color: SERIES.modis, opacity: 0.18 }, itemStyle: { color: SERIES.modis } },
      { name: "Median", type: "line", data: cl.map((c) => c.median), itemStyle: { color: SERIES.modis }, lineStyle: { width: 2 }, symbol: "circle", symbolSize: 4 },
      { name: String(year), type: "line", data: cl.map((c) => c.current), itemStyle: { color: SERIES.current }, lineStyle: { width: 2.5 }, symbol: "diamond", symbolSize: 7 },
    ],
  };
  return <div className="chart"><ReactECharts option={option} style={{ height: 240 }} /></div>;
}
