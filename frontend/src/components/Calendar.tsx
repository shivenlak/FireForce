import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { INFERNO_R, MONTHS, NODATA, RDBU, ZERO, fmt, interp, pct, textOn } from "../colors";
import type { CalendarCell, CalendarResponse } from "../types";

interface Props {
  data: CalendarResponse;
  color: "counts" | "anomaly";
  numbers: boolean;
  onSelect?: (c: CalendarCell) => void;
}

const FLAG_TEXT: Record<string, string> = {
  terra_only: "Terra-only MODIS (pre-Aqua), corrected with Terra→Terra+Aqua factor",
  gap_filled: "VIIRS outage this month; value from MODIS",
  partial: "Partial month (data so far)",
};

// Anomaly is colored by log2(value / median), clamped to ±3 (1/8× … 8×): symmetric for
// "half as much" vs "twice as much", which a raw percent scale is not.
const LOG2_MAX = 3;

export function cellColor(c: CalendarCell, color: "counts" | "anomaly", vmax: number, median: number | null): string {
  if (c.value === null) return NODATA;
  if (color === "counts") {
    if (c.value <= 0) return ZERO;
    return interp(INFERNO_R, Math.log10(1 + c.value) / Math.log10(1 + vmax));
  }
  if (median === null || median < 1) return ZERO;
  const r = Math.log2((c.value + 0.5) / (median + 0.5));
  return interp(RDBU, (r + LOG2_MAX) / (2 * LOG2_MAX));
}

export default function Calendar({ data, color, numbers, onSelect }: Props) {
  const years = data.years;
  const vmax = useMemo(() => Math.max(1, ...data.cells.map((c) => c.value ?? 0)), [data]);

  const option = useMemo(() => {
    // ECharts heatmaps require a visualMap; we compute each cell's color ourselves and map it
    // through a hidden piecewise visualMap keyed by palette index (dimension 3).
    const palette: string[] = [];
    const paletteIndex = (col: string) => {
      let i = palette.indexOf(col);
      if (i < 0) { palette.push(col); i = palette.length - 1; }
      return i;
    };
    const items = data.cells.map((c) => {
      const med = data.baseline_median[c.month - 1];
      const bg = cellColor(c, color, vmax, med);
      const flagged = c.flags.filter((f) => f !== "no_data");
      return {
        value: [c.month - 1, years.indexOf(c.year), c.value ?? "-", paletteIndex(bg)],
        cell: c,
        itemStyle: {
          color: bg,
          borderColor: flagged.includes("partial") ? "#111" : "#fff",
          borderWidth: flagged.includes("partial") ? 2 : 1,
          borderType: flagged.includes("partial") ? "dashed" : "solid",
          decal: flagged.includes("terra_only") || flagged.includes("gap_filled")
            ? {
                symbol: "rect",
                color: textOn(bg) === "#fff" ? "rgba(255,255,255,0.45)" : "rgba(0,0,0,0.35)",
                dashArrayX: [1, 0],
                dashArrayY: flagged.includes("terra_only") ? [2, 4] : [1, 6],
                rotation: flagged.includes("terra_only") ? -Math.PI / 4 : Math.PI / 4,
              }
            : undefined,
        },
        label: {
          color: textOn(bg),
          formatter: () => {
            if (c.value === null) return "";
            return color === "anomaly" ? pct(c.anomaly_pct) : fmt(c.value);
          },
        },
      };
    });
    return {
      animation: false,
      aria: { enabled: true, label: { description: `Burning activity calendar, years ${years[0]} to ${years[years.length - 1]} as rows and months as columns.` } },
      grid: { top: 28, left: 46, right: 40, bottom: 8 },
      toolbox: {
        right: 0, top: 0,
        feature: { saveAsImage: { title: "Save PNG", name: "firecal_calendar", pixelRatio: 2, backgroundColor: "#fff" } },
      },
      tooltip: {
        confine: true,
        formatter: (p: { data: { cell: CalendarCell } }) => {
          const c = p.data.cell;
          const med = data.baseline_median[c.month - 1];
          if (c.value === null) return `<b>${MONTHS[c.month - 1]} ${c.year}</b><br/>No data / outside selected range`;
          const flags = c.flags.filter((f) => f !== "no_data").map((f) => `<div style="color:#a52c60">⚑ ${FLAG_TEXT[f]}</div>`).join("");
          return `<b>${MONTHS[c.month - 1]} ${c.year}</b><br/>
            ${fmt(c.value, 1)} ${data.units}<br/>
            Baseline median: ${fmt(med, 1)}<br/>
            Anomaly: <b>${pct(c.anomaly_pct)}</b>${c.zscore !== null ? ` (robust z ${c.zscore.toFixed(1)})` : ""}<br/>
            Source: ${c.source ?? "—"} · ${c.detections.toLocaleString()} detections${flags}`;
        },
      },
      xAxis: {
        type: "category", data: MONTHS, position: "top", splitArea: { show: false },
        axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#333", fontWeight: 600 },
      },
      yAxis: {
        type: "category", data: years.map(String), inverse: true,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: "#333", fontFamily: "ui-monospace, Menlo, monospace", fontSize: 11 },
      },
      visualMap: {
        show: false, type: "piecewise", dimension: 3, seriesIndex: 0,
        pieces: palette.map((col, i) => ({ value: i, color: col })),
      },
      series: [{
        type: "heatmap",
        data: items,
        label: { show: numbers, fontSize: 9 },
        emphasis: { itemStyle: { borderColor: "#000", borderWidth: 2 } },
        progressive: 0,
      }],
    };
  }, [data, color, numbers, vmax, years]);

  const height = Math.max(320, years.length * 20 + 40);
  return (
    <div>
      <ReactECharts
        option={option}
        style={{ height, width: "100%" }}
        notMerge
        onEvents={{ click: (p: { data: { cell: CalendarCell } }) => onSelect?.(p.data.cell) }}
      />
      <Legend color={color} vmax={vmax} units={data.units} />
      <details className="table-view">
        <summary>Show calendar as a table (screen-reader friendly)</summary>
        <div className="table-scroll">
          <table className="tbl">
            <caption className="muted small">{data.units}; anomaly vs. baseline median in brackets; ⚑ = flagged</caption>
            <thead><tr><th scope="col">Year</th>{MONTHS.map((m) => <th scope="col" key={m}>{m}</th>)}</tr></thead>
            <tbody>
              {years.map((y) => (
                <tr key={y}>
                  <th scope="row">{y}</th>
                  {data.cells.filter((c) => c.year === y).map((c) => (
                    <td key={c.month}>
                      {c.value === null ? "—" : `${fmt(c.value)} (${pct(c.anomaly_pct)})`}
                      {c.flags.some((f) => f !== "no_data") ? " ⚑" : ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function Legend({ color, vmax, units }: { color: "counts" | "anomaly"; vmax: number; units: string }) {
  const stops = Array.from({ length: 24 }, (_, i) => i / 23);
  const ramp = color === "counts" ? INFERNO_R : RDBU;
  const labels = color === "counts"
    ? [0, Math.round(Math.sqrt(vmax)), Math.round(vmax)].map((v) => fmt(v))
    : ["−88% (⅛×)", "normal", "+700% (8×)"];
  return (
    <div className="legend" role="img" aria-label={color === "counts" ? `Color scale: log scale from 0 to ${fmt(vmax)} ${units}` : "Color scale: anomaly from one eighth of normal to eight times normal"}>
      <div className="legend-bar">
        {stops.map((t) => <span key={t} style={{ background: interp(ramp, t) }} />)}
      </div>
      <div className="legend-labels">{labels.map((l) => <span key={l}>{l}</span>)}</div>
      <div className="legend-keys">
        <span><i className="swatch" style={{ background: ZERO }} /> zero</span>
        <span><i className="swatch hatch-terra" /> Terra-only (2000–02)</span>
        <span><i className="swatch hatch-gap" /> VIIRS outage → MODIS</span>
        <span><i className="swatch partial" /> partial month</span>
        <span className="muted">{color === "counts" ? `${units}, log scale` : "vs. baseline median for that month"}</span>
      </div>
    </div>
  );
}
