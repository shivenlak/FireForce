"""DuckDB queries over the processed (or sample) Parquet data."""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
UNITS = {"harmonized": "MODIS-equivalent fire cell-days",
         "modis": "MODIS fire cell-days (raw, uncalibrated)",
         "viirs": "VIIRS S-NPP fire cell-days (raw, uncalibrated)"}
HOTSPOT_CAP = 500_000


def data_dir() -> Path:
    if os.getenv("DATA_DIR"):
        return Path(os.environ["DATA_DIR"]).resolve()
    processed = ROOT / "data" / "processed"
    if (processed / "detections").exists():
        return processed
    return ROOT / "data" / "sample"


class Store:
    """Holds a DuckDB connection + small metadata tables. One per process."""

    def __init__(self, root: Path):
        self.root = root
        self.con = duckdb.connect()
        self.con.execute("INSTALL spatial; LOAD spatial;")
        self.lock = threading.Lock()
        det = root / "detections"
        self.countries = sorted(p.name.split("=", 1)[1] for p in det.glob("country=*")) if det.exists() else []
        if self.countries:
            self.con.execute(f"""CREATE VIEW det AS SELECT * FROM read_parquet(
                '{det}/**/*.parquet', hive_partitioning=true, union_by_name=true)""")
        months = [pd.read_parquet(p) for p in sorted((root / "months").glob("*.parquet"))]
        self.months = pd.concat(months, ignore_index=True) if months else pd.DataFrame()
        self.calibration = _read_json(root / "calibration.json")
        self.validation = _read_json(root / "validation.json")
        geo_path = root / "countries.geojson"
        if not geo_path.exists():
            geo_path = ROOT / "data" / "sample" / "countries.geojson"
        self.geo = _read_json(geo_path) or {"features": []}
        self.default = _read_json(root / "sample.json") or {
            "bbox": [-121.5, 49.0, -118.5, 52.0], "label": "Kelowna-Kamloops, British Columbia"}
        ends = [v.get("last_date") for v in self.calibration.values() if v.get("last_date")]
        self.data_end = dt.date.fromisoformat(max(ends)) if ends else dt.date.today()

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        with self.lock:
            return self.con.execute(sql, params or []).df()

    def cursor(self) -> duckdb.DuckDBPyConnection:
        return self.con.cursor()


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


@lru_cache(maxsize=1)
def store() -> Store:
    return Store(data_dir())


# ------------------------------------------------------------------ AOI handling
def _geometry(aoi: dict | None) -> dict | None:
    if not aoi:
        return None
    if aoi.get("type") == "Feature":
        return aoi["geometry"]
    if aoi.get("type") == "FeatureCollection":
        geoms = [f["geometry"] for f in aoi["features"]]
        return geoms[0] if len(geoms) == 1 else {"type": "GeometryCollection", "geometries": geoms}
    return aoi


def _coords(obj: Any) -> Iterator[tuple[float, float]]:
    if isinstance(obj, (list, tuple)) and obj and isinstance(obj[0], (int, float)):
        yield float(obj[0]), float(obj[1])
    elif isinstance(obj, (list, tuple)):
        for o in obj:
            yield from _coords(o)
    elif isinstance(obj, dict):
        yield from _coords(obj.get("coordinates") or obj.get("geometries") or [])


def bbox_of(geom: dict) -> list[float]:
    pts = list(_coords(geom))
    if not pts:
        raise ValueError("AOI geometry has no coordinates")
    xs, ys = zip(*pts)
    return [min(xs), min(ys), max(xs), max(ys)]


def _bbox_intersects(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


class Selection:
    """Translates an AOI request into a SQL WHERE clause + params."""

    def __init__(self, s: Store, aoi: dict | None, country: str | None,
                 start: dt.date | None = None, end: dt.date | None = None):
        self.geom = _geometry(aoi)
        if country and country not in s.countries:
            raise ValueError(f"Country '{country}' has no processed data. Available: {s.countries}")
        if not self.geom and not country:
            raise ValueError("Provide an AOI geometry or a country")
        self.bbox = bbox_of(self.geom) if self.geom else region_bbox(s, country)
        if country:
            self.countries = [country]
        else:
            self.countries = [c for c in s.countries if _bbox_intersects(self.bbox, region_bbox(s, c))]
        self.start, self.end = start, end
        self.where, self.params = self._build()

    def _build(self) -> tuple[str, list]:
        if not self.countries:
            return "FALSE", []
        clauses = [f"country IN ({','.join('?' * len(self.countries))})"]
        params: list = list(self.countries)
        if self.geom:
            w, s, e, n = self.bbox
            clauses.append("latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?")
            params += [s, n, w, e]
            if self.geom.get("type") != "Polygon" or not _is_axis_rect(self.geom):
                clauses.append("ST_Contains(ST_GeomFromGeoJSON(?), ST_Point(longitude, latitude))")
                params.append(json.dumps(self.geom))
        return " AND ".join(clauses), params

    def date_clause(self) -> tuple[str, list]:
        c, p = [], []
        if self.start:
            c.append("acq_date >= ?"); p.append(self.start)
        if self.end:
            c.append("acq_date <= ?"); p.append(self.end)
        return (" AND " + " AND ".join(c) if c else ""), p


def _is_axis_rect(geom: dict) -> bool:
    """Axis-aligned rectangles are fully handled by the bbox prefilter (fast path)."""
    ring = geom["coordinates"][0]
    corners = {(round(p[0], 9), round(p[1], 9)) for p in ring}
    xs = {c[0] for c in corners}
    ys = {c[1] for c in corners}
    return len(geom["coordinates"]) == 1 and len(xs) == 2 and len(ys) == 2 and len(corners) == 4


def region_bbox(s: Store, name: str) -> list[float]:
    for f in s.geo["features"]:
        if f["properties"]["name"] == name:
            return f["properties"]["bbox"]
    return [-180.0, -90.0, 180.0, 90.0]


def regions(s: Store) -> list[dict]:
    out = []
    for f in s.geo["features"]:
        p = f["properties"]
        out.append({"name": p["name"], "label": p["label"], "iso3": p["iso3"], "bbox": p["bbox"],
                    "has_data": p["name"] in s.countries})
    return sorted(out, key=lambda r: (not r["has_data"], r["label"]))


def region_geometry(s: Store, name: str) -> dict | None:
    for f in s.geo["features"]:
        if f["properties"]["name"] == name:
            return f
    return None


# ------------------------------------------------------------------ core aggregation
def _weight_expr(mode: str) -> str:
    return {"harmonized": "harmonized_weight",
            "modis": "CASE WHEN sensor='MODIS' THEN cellday_weight ELSE 0 END",
            "viirs": "CASE WHEN sensor='VIIRS' THEN cellday_weight ELSE 0 END"}[mode]


def monthly(s: Store, sel: Selection, mode: str) -> pd.DataFrame:
    """Full-history monthly values for the AOI (date range is applied later, for display)."""
    df = s.query(f"""
      SELECT year(acq_date) AS year, month(acq_date) AS month,
             sum({_weight_expr(mode)}) AS value,
             count(*) FILTER (WHERE {_weight_expr(mode)} > 0) AS detections,
             sum(CASE WHEN sensor='MODIS' THEN harmonized_weight ELSE 0 END) AS h_modis,
             sum(CASE WHEN sensor='VIIRS' THEN harmonized_weight ELSE 0 END) AS h_viirs
      FROM det WHERE {sel.where} GROUP BY 1, 2
    """, sel.params)
    return df


def month_meta(s: Store, countries: list[str]) -> pd.DataFrame:
    """Per-month flags/source, merged across countries in the AOI."""
    m = s.months[s.months["country"].isin(countries)].copy()
    if m.empty:
        return pd.DataFrame(columns=["ym", "terra_only", "gap_filled", "partial", "source"])
    m["viirs_src"] = m["source"] == "VIIRS"
    g = m.groupby("ym").agg(terra_only=("terra_only", "any"), gap_filled=("gap_filled", "any"),
                            partial=("partial", "any"), viirs_src=("viirs_src", "all"))
    g["source"] = np.where(g["viirs_src"], "VIIRS", "MODIS")
    return g.drop(columns="viirs_src").reset_index()


def _full_grid(s: Store, sel: Selection, mode: str) -> pd.DataFrame:
    """year x month grid over the data record, 0-filled where no detections."""
    meta = month_meta(s, sel.countries)
    if meta.empty:
        return pd.DataFrame()
    m = monthly(s, sel, mode)
    grid = meta.assign(year=meta["ym"].str[:4].astype(int), month=meta["ym"].str[5:7].astype(int))
    grid = grid.merge(m, on=["year", "month"], how="left").fillna(
        {"value": 0.0, "detections": 0, "h_modis": 0.0, "h_viirs": 0.0})
    if mode == "viirs":
        grid.loc[grid["ym"] < "2012-01", "value"] = np.nan
    return grid


def _baseline_years(grid: pd.DataFrame, data_end: dt.date, b0: int | None, b1: int | None) -> list[int]:
    counts = grid.dropna(subset=["value"]).groupby("year").size()
    complete = [int(y) for y, n in counts.items() if n == 12 and y < data_end.year]
    if b0:
        complete = [y for y in complete if y >= b0]
    if b1:
        complete = [y for y in complete if y <= b1]
    return complete


def _anomaly(v, med, mad):
    if v is None or med is None or np.isnan(v) or med < 1:
        return None, None
    pct = (v - med) / med * 100
    z = (v - med) / (1.4826 * mad) if mad and mad > 0 else None
    return float(pct), (float(z) if z is not None else None)


def calendar(s: Store, req) -> dict:
    sel = Selection(s, req.aoi, req.country)
    grid = _full_grid(s, sel, req.mode)
    if grid.empty:
        return {"mode": req.mode, "units": UNITS[req.mode], "years": [], "cells": [],
                "baseline_median": [None] * 12, "baseline_years": [], "countries": sel.countries,
                "data_end": s.data_end}
    years = _baseline_years(grid, s.data_end, req.baseline_start, req.baseline_end)
    base = grid[grid["year"].isin(years)]
    med = base.groupby("month")["value"].median()
    mad = base.groupby("month")["value"].apply(lambda x: float(np.median(np.abs(x - x.median()))))
    start = req.start or dt.date(1900, 1, 1)
    end = req.end or dt.date(2999, 12, 31)
    lookup = grid.set_index(["year", "month"])
    y_min, y_max = int(grid["year"].min()), int(grid["year"].max())
    cells = []
    for y in range(y_min, y_max + 1):
        for mth in range(1, 13):
            in_range = (start.year, start.month) <= (y, mth) <= (end.year, end.month)
            if (y, mth) not in lookup.index or not in_range:
                cells.append({"year": y, "month": mth, "value": None, "anomaly_pct": None, "zscore": None,
                              "detections": 0, "source": None, "flags": ["no_data"]})
                continue
            r = lookup.loc[(y, mth)]
            v = None if pd.isna(r["value"]) else float(r["value"])
            pct, z = _anomaly(v, med.get(mth), mad.get(mth))
            flags = [f for f in ("terra_only", "gap_filled", "partial") if bool(r[f])]
            if v is None:
                flags.append("no_data")
            src = r["source"] if req.mode == "harmonized" else req.mode.upper()
            cells.append({"year": y, "month": mth, "value": v, "anomaly_pct": pct, "zscore": z,
                          "detections": int(r["detections"]), "source": src, "flags": flags})
    return {"mode": req.mode, "units": UNITS[req.mode], "years": list(range(y_min, y_max + 1)),
            "cells": cells, "baseline_median": [None if pd.isna(med.get(m)) else float(med.get(m))
                                                for m in range(1, 13)],
            "baseline_years": [min(years), max(years)] if years else [],
            "countries": sel.countries, "data_end": s.data_end}


def summary(s: Store, req) -> dict:
    sel = Selection(s, req.aoi, req.country, req.start, req.end)
    grid = _full_grid(s, sel, req.mode)
    out = {"mode": req.mode, "units": UNITS[req.mode], "current": None, "peak_months": [],
           "peak_years": [], "annual": [], "climatology": [],
           "sensor_share": {"detections": {}, "harmonized": {}}, "total": 0.0}
    if grid.empty:
        return out
    end = s.data_end
    years = _baseline_years(grid, end, req.baseline_start, req.baseline_end)
    g = grid.dropna(subset=["value"])
    rng = g
    if req.start:
        rng = rng[(rng["year"] * 100 + rng["month"]) >= req.start.year * 100 + req.start.month]
    if req.end:
        rng = rng[(rng["year"] * 100 + rng["month"]) <= req.end.year * 100 + req.end.month]

    # month-to-date vs same day range in all past years
    w = _weight_expr(req.mode)
    mtd = s.query(f"""
      SELECT year(acq_date) AS year, sum({w}) AS value FROM det
      WHERE {sel.where} AND month(acq_date) = ? AND day(acq_date) <= ? GROUP BY 1
    """, sel.params + [end.month, end.day])
    yrs_avail = sorted(set(g.loc[g["month"] == end.month, "year"]))
    hist = pd.Series(0.0, index=yrs_avail)
    hist.update(mtd.set_index("year")["value"])
    if end.year in hist.index:
        cur = float(hist[end.year])
        past = hist.drop(end.year)
        base_past = past[past.index.isin(years)] if years else past
        median = float(base_past.median()) if len(base_past) else None
        rank = int((hist > cur).sum() + 1)
        pct, _ = _anomaly(cur, median, None)
        out["current"] = {
            "year": end.year, "month": end.month, "day": end.day, "value": cur, "median": median,
            "anomaly_pct": pct, "rank": rank, "n_years": int(len(hist)),
            "percentile": float((past < cur).mean() * 100) if len(past) else None,
            "history": [{"year": int(y), "value": float(v), "partial": False} for y, v in hist.items()],
        }

    complete_months = rng[~rng["partial"]]
    top = complete_months.nlargest(3, "value")
    out["peak_months"] = [{"year": int(r.year), "month": int(r.month), "value": float(r.value)}
                          for r in top.itertuples()]
    ann = rng.groupby("year").agg(value=("value", "sum"), n=("month", "size"),
                                  partial=("partial", "any")).reset_index()
    ann["partial"] = ann["partial"] | (ann["n"] < 12)
    out["annual"] = [{"year": int(r.year), "value": float(r.value), "partial": bool(r.partial)}
                     for r in ann.itertuples()]
    out["peak_years"] = [{"year": int(r.year), "value": float(r.value), "partial": bool(r.partial)}
                         for r in ann[~ann["partial"]].nlargest(3, "value").itertuples()]
    base = g[g["year"].isin(years)]
    cur_year = g[g["year"] == end.year].set_index("month")["value"]
    for m in range(1, 13):
        b = base.loc[base["month"] == m, "value"]
        out["climatology"].append({
            "month": m,
            "median": float(b.median()) if len(b) else None,
            "q25": float(b.quantile(.25)) if len(b) else None,
            "q75": float(b.quantile(.75)) if len(b) else None,
            "current": float(cur_year[m]) if m in cur_year.index else None,
        })
    dc, dp = sel.date_clause()
    share = s.query(f"""
      SELECT sensor, count(*) AS n, sum(harmonized_weight) AS h FROM det
      WHERE {sel.where}{dc} GROUP BY 1
    """, sel.params + dp)
    tot_h = float(share["h"].sum()) or 1.0
    out["sensor_share"] = {"detections": {r.sensor: int(r.n) for r in share.itertuples()},
                           "harmonized": {r.sensor: float(r.h) / tot_h for r in share.itertuples()}}
    out["total"] = float(rng["value"].sum())
    return out


def points(s: Store, req, max_points: int = 6000) -> dict:
    sel = Selection(s, req.aoi, req.country, req.start, req.end)
    w, so, e, n = sel.bbox
    span = max(e - w, n - so)
    dc, dp = sel.date_clause()
    wexpr = _weight_expr(req.mode)
    for res in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0):
        if span / res > 600 and res < 1.0:
            continue
        df = s.query(f"""
          SELECT (floor(latitude/{res}) + 0.5) * {res} AS lat, (floor(longitude/{res}) + 0.5) * {res} AS lon,
                 sum({wexpr}) AS v, count(*) AS n
          FROM det WHERE {sel.where}{dc} AND {wexpr} > 0 GROUP BY 1, 2
        """, sel.params + dp)
        if len(df) <= max_points or res == 1.0:
            break
    df = df.nlargest(max_points, "v")
    return {"resolution_deg": res, "total_detections": int(df["n"].sum()),
            "points": df[["lat", "lon", "v", "n"]].round(4).values.tolist()}


HOTSPOT_COLUMNS = ["country", "sensor", "satellite", "latitude", "longitude", "acq_date", "acq_time",
                   "confidence", "daynight", "frp", "data_source", "cell_id", "n_det_cellday",
                   "cellday_weight", "calibrated_weight", "harmonized_weight"]


def hotspots_csv(s: Store, req, cap: int = HOTSPOT_CAP) -> Iterator[str]:
    sel = Selection(s, req.aoi, req.country, req.start, req.end)
    dc, dp = sel.date_clause()
    cur = s.cursor()
    cur.execute(f"""SELECT {', '.join(HOTSPOT_COLUMNS)} FROM det WHERE {sel.where}{dc}
                    ORDER BY acq_date, acq_time LIMIT {cap}""", sel.params + dp)
    yield ",".join(HOTSPOT_COLUMNS) + "\n"
    while True:
        rows = cur.fetchmany(20000)
        if not rows:
            break
        yield "".join(",".join("" if v is None else str(v) for v in r) + "\n" for r in rows)


def calendar_csv(s: Store, req) -> str:
    cal = calendar(s, req)
    lines = ["year,month,value,baseline_median,anomaly_pct,robust_z,detections,source,flags,units"]
    for c in cal["cells"]:
        if c["value"] is None:
            continue
        med = cal["baseline_median"][c["month"] - 1]
        f = lambda v: "" if v is None else f"{v:.4f}"  # noqa: E731
        lines.append(f"{c['year']},{c['month']},{f(c['value'])},{f(med)},{f(c['anomaly_pct'])},"
                     f"{f(c['zscore'])},{c['detections']},{c['source'] or ''},{'|'.join(c['flags'])},"
                     f"{cal['units']}")
    return "\n".join(lines) + "\n"
