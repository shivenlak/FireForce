"""Steps 2-4: grid, calibrate (choose grid + model by leave-one-year-out), flag, weight, write.

Usage: python -m pipeline.build --countries Canada
Outputs (data/processed/):
  detections/country=*/sensor=*/year=*/*.parquet  cleaned detections + cell_id + weights
  months/{country}.parquet                        monthly series, source choice and flags
  calibration.json                                coefficients, fit stats, grid/model choice
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import duckdb
import numpy as np
import pandas as pd

from pipeline import calibrate as cal
from pipeline import config
from pipeline.clean import clean_country, connect
from pipeline.grid import cell_expr, monthly_celldays_sql

OUTAGE_OTHER_MIN = 5    # VIIRS outage day: zero VIIRS while MODIS has >= this many raw detections
OUTAGE_MODIS_OTHER_MIN = 200  # MODIS outage day: zero MODIS while VIIRS >= this (VIIRS sees small flares MODIS misses)
OUTAGE_MIN_DAYS = 2     # month flagged if it has >= this many outage days


def monthly_table(con: duckdb.DuckDBPyConnection, clean_path: str, g: float) -> pd.DataFrame:
    return con.execute(monthly_celldays_sql(f"'{clean_path}'", g)).df()


def outage_days(daily_path: str) -> pd.DataFrame:
    """Days where one sensor has zero raw detections while the other has plenty."""
    d = pd.read_parquet(daily_path).pivot_table(index="acq_date", columns="sensor",
                                                values="n_all", fill_value=0)
    d.index = pd.to_datetime(d.index)
    full = pd.date_range(d.index.min(), d.index.max(), freq="D")
    d = d.reindex(full, fill_value=0)
    for s in ("MODIS", "VIIRS", "VIIRS_N20"):
        if s not in d:
            d[s] = 0
    starts = {"VIIRS": pd.Timestamp("2012-01-20"), "VIIRS_N20": pd.Timestamp(config.N20_START + "-01")}
    rows = []
    for day, r in d.iterrows():
        for s, st in starts.items():
            if r[s] == 0 and r["MODIS"] >= OUTAGE_OTHER_MIN and day >= st:
                rows.append((day, s))
        if r["MODIS"] == 0 and max(r["VIIRS"], r["VIIRS_N20"]) >= OUTAGE_MODIS_OTHER_MIN:
            rows.append((day, "MODIS"))
    # trailing days after a sensor's last data (e.g. NRT feed ended) also count as outage
    end = d.index.max()
    for s in ("MODIS", "VIIRS", "VIIRS_N20"):
        if not (d[s] > 0).any():
            continue
        ld = d.index[d[s] > 0].max()
        for day in pd.date_range(ld + pd.Timedelta(days=1), end, freq="D"):
            rows.append((day, s))
    out = pd.DataFrame(rows, columns=["date", "sensor"]).drop_duplicates()
    out["date"] = pd.to_datetime(out["date"])
    out["ym"] = out["date"].dt.strftime("%Y-%m")
    return out


def select_model(monthlies: dict[float, pd.DataFrame], start: str, end: str) -> dict:
    results = {}
    for g, m in monthlies.items():
        ov = cal.in_window(m, start, end)
        for method in cal.FITS:
            res, _ = cal.loyo(ov, method)
            ak = cal.annual_k(ov)
            res["k_cv"] = float(ak["k"].std() / ak["k"].mean())
            results[f"{g}|{method}"] = res
    # Score = monthly MAPE + |bias|: penalizes systematic bias, which would distort long-term trends.
    for r in results.values():
        r["score"] = r["mape"] + abs(r["bias_pct"])
    best = min(results, key=lambda k: results[k]["score"])
    g, method = best.split("|")
    return {"grid_deg": float(g), "method": method, "candidates": results}


def build_country(country: str, skip_clean: bool = False) -> dict:
    con = connect()
    if not skip_clean:
        clean_country(country, con)
    clean_path = str(config.PROCESSED / "clean" / f"{country}.parquet")
    daily_path = str(config.PROCESSED / "clean" / f"{country}_daily_raw.parquet")

    monthlies = {g: monthly_table(con, clean_path, g) for g in config.GRID_CANDIDATES}
    choice = select_model(monthlies, config.OVERLAP_START, config.OVERLAP_END)
    g, method = choice["grid_deg"], choice["method"]
    months = monthlies[g].copy()
    overlap = cal.in_window(months, config.OVERLAP_START, config.OVERLAP_END)
    model = cal.FITS[method][0](overlap)
    tf = cal.terra_factor(months)
    # NOAA-20: same ratio model, fit on its own overlap with MODIS (N20_START .. OVERLAP_END)
    has_n20 = months["N"].sum() > 0
    n_ov = cal.in_window(months, config.N20_START, config.OVERLAP_END).assign(V=lambda x: x["N"])
    n20_model = cal.fit_ratio(n_ov) if has_n20 else None

    # ---- flags + harmonized monthly series
    out = outage_days(daily_path)
    last_date = pd.to_datetime(con.execute(f"SELECT max(acq_date) FROM '{clean_path}'").fetchall()[0][0])
    moy = months["ym"].str[5:7].astype(int)
    months["terra_only"] = months["ym"] < "2002-07"
    months["terra_factor"] = np.where(months["terra_only"], moy.map(tf["months"]), 1.0)
    months["M_adj"] = months["M"] * months["terra_factor"]
    months["V_cal"] = cal.predict(model, months)
    months["N_cal"] = cal.predict_ratio(n20_model, months.assign(V=months["N"])) if has_n20 else 0.0
    months["viirs_outage_days"] = months["ym"].map(out[out.sensor == "VIIRS"].groupby("ym").size()).fillna(0).astype(int)
    months["n20_outage_days"] = months["ym"].map(out[out.sensor == "VIIRS_N20"].groupby("ym").size()).fillna(0).astype(int)
    months["modis_outage_days"] = months["ym"].map(out[out.sensor == "MODIS"].groupby("ym").size()).fillna(0).astype(int)
    months["partial"] = months["ym"] == last_date.strftime("%Y-%m")
    viirs_era = months["ym"] >= f"{config.SWITCH_YEAR}-02"  # S-NPP data start 2012-01-20
    viirs_bad = months["viirs_outage_days"] >= OUTAGE_MIN_DAYS
    modis_ok = months["modis_outage_days"] < OUTAGE_MIN_DAYS
    n20_ok = (months["ym"] >= config.N20_START) & (months["n20_outage_days"] < OUTAGE_MIN_DAYS) & (months["N"] > 0)
    # Source cascade in the VIIRS era: S-NPP -> NOAA-20 (calibrated) -> MODIS -> S-NPP anyway.
    months["source"] = np.select(
        [~viirs_era, ~viirs_bad, n20_ok, modis_ok & (months["M"] > 0)],
        ["MODIS", "VIIRS", "VIIRS_N20", "MODIS"], default="VIIRS")
    months["gap_filled"] = viirs_era & (months["source"] != "VIIRS")
    months["H"] = np.select([months["source"] == "VIIRS", months["source"] == "VIIRS_N20"],
                            [months["V_cal"], months["N_cal"]], default=months["M_adj"])
    months["country"] = country
    (config.PROCESSED / "months").mkdir(parents=True, exist_ok=True)
    months.to_parquet(config.PROCESSED / "months" / f"{country}.parquet", index=False)

    # ---- per-detection weights
    # MODIS: terra_factor / n_det   VIIRS: (V_cal / V) / n_det  (= (1/k)/n_det for ratio model)
    wt = months[["ym", "terra_factor", "source"]].copy()
    wt["viirs_scale"] = np.where(months["V"] > 0, months["V_cal"] / months["V"].replace(0, 1), 0.0)
    wt["n20_scale"] = np.where(months["N"] > 0, months["N_cal"] / months["N"].replace(0, 1), 0.0)
    con.register("wt", wt)
    det_dir = config.PROCESSED / "detections"
    country_dir = det_dir / f"country={country}"
    if country_dir.exists():
        import shutil
        shutil.rmtree(country_dir)
    con.execute(f"""
      COPY (
        WITH d AS (
          SELECT *, {cell_expr(g)} AS cell_id, strftime(acq_date, '%Y-%m') AS ym FROM '{clean_path}'
        ), n AS (
          SELECT *, count(*) OVER (PARTITION BY sensor, cell_id, acq_date) AS n_det_cellday FROM d
        )
        SELECT n.country, n.sensor, year(n.acq_date) AS year,
               n.latitude, n.longitude, n.acq_date, n.acq_time, n.satellite, n.confidence,
               n.daynight, n.frp, n.source AS data_source, n.cell_id, n.n_det_cellday,
               1.0 / n.n_det_cellday AS cellday_weight,
               CASE n.sensor WHEN 'MODIS' THEN wt.terra_factor WHEN 'VIIRS' THEN wt.viirs_scale ELSE wt.n20_scale END
                 / n.n_det_cellday AS calibrated_weight,
               CASE WHEN n.sensor = wt.source THEN
                 CASE n.sensor WHEN 'MODIS' THEN wt.terra_factor WHEN 'VIIRS' THEN wt.viirs_scale ELSE wt.n20_scale END / n.n_det_cellday
               ELSE 0 END AS harmonized_weight
        FROM n JOIN wt USING (ym)
      ) TO '{det_dir}' (FORMAT parquet, PARTITION_BY (country, sensor, year), OVERWRITE_OR_IGNORE, COMPRESSION zstd)
    """)

    # ---- calibration.json (merge per country)
    cal_path = config.PROCESSED / "calibration.json"
    allcal = json.loads(cal_path.read_text()) if cal_path.exists() else {}
    allcal[country] = {
        "built": dt.datetime.now().isoformat(timespec="seconds"),
        "grid_deg": g, "method": method,
        "overlap": [config.OVERLAP_START, config.OVERLAP_END],
        "model": model, "terra_factor": tf, "n20_model": n20_model,
        "selection": {k: {kk: vv for kk, vv in v.items() if kk != "per_year"}
                      for k, v in choice["candidates"].items()},
        "annual_k": {str(gg): cal.annual_k(m).round(4).to_dict(orient="records")
                     for gg, m in monthlies.items()},
        "outage_days": out.assign(date=out["date"].dt.strftime("%Y-%m-%d"))[["date", "sensor"]].to_dict(orient="records"),
        "last_date": last_date.strftime("%Y-%m-%d"),
    }
    cal_path.write_text(json.dumps(allcal, indent=1, default=float))
    print(f"{country}: grid={g} method={method} LOYO MAPE={choice['candidates'][f'{g}|{method}']['mape']:.1f}%")
    return allcal[country]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="Canada")
    ap.add_argument("--skip-clean", action="store_true")
    a = ap.parse_args()
    for c in a.countries.split(","):
        build_country(c, a.skip_clean)
