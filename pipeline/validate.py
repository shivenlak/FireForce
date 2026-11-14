"""Step 5: validation -> data/processed/validation.json (served by /api/validation).

Per country:
  * leave-one-year-out (LOYO) skill of the chosen model + all grid/model candidates
  * baseline: same ratio model on RAW detection counts (no cell-day unit) -> shows why we grid
  * sensitivity: overlap ending 2022 (pre orbit-drift) vs the default window
  * forward test: fit 2012-2019, predict 2020-2025 (incl. the record 2023 season)
  * Aqua-only vs S-NPP (similar ~13:30 overpass) agreement
  * monthly series for plots: raw detections, cell-days, harmonized
  * invariant: sum of per-detection harmonized_weight == harmonized monthly series
"""
from __future__ import annotations

import argparse
import json

import duckdb
import numpy as np
import pandas as pd

from pipeline import calibrate as cal
from pipeline import config


def _r(x, n=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def _clean(d: dict) -> dict:
    return {k: (_r(v) if isinstance(v, float) else v) for k, v in d.items() if k != "per_year"}


def validate_country(country: str, calib: dict) -> dict:
    months = pd.read_parquet(config.PROCESSED / "months" / f"{country}.parquet")
    start, end = calib["overlap"]
    method = calib["method"]
    clean_month = (months["viirs_outage_days"] == 0) & (months["modis_outage_days"] == 0)
    ov = cal.in_window(months[clean_month], start, end)

    chosen, res = cal.loyo(ov, method)
    raw = ov.assign(M=ov["det_M"], V=ov["det_V"])
    raw_loyo, _ = cal.loyo(raw, "ratio")
    raw_k = cal.annual_k(raw)
    cd_k = cal.annual_k(ov)

    sens_ov = cal.in_window(months[clean_month], start, config.OVERLAP_END_SENSITIVITY)
    sens, _ = cal.loyo(sens_ov, method)

    fit, pred = cal.FITS[method]
    train = cal.in_window(months[clean_month], start, "2019-12")
    test = cal.in_window(months[clean_month], "2020-01", end)
    fwd_pred = pred(fit(train), test)
    forward = cal.metrics(test["M"].to_numpy(), fwd_pred)
    forward_annual = (test.assign(pred=fwd_pred, year=test["ym"].str[:4])
                      .groupby("year")[["M", "pred"]].sum().round(0).reset_index().to_dict(orient="records"))

    n20 = None
    if months.get("N") is not None and months["N"].sum() > 0:
        n_clean = (months["n20_outage_days"] == 0) & (months["modis_outage_days"] == 0)
        n_ov = cal.in_window(months[n_clean], config.N20_START, end).assign(V=lambda x: x["N"])
        n_loyo, _ = cal.loyo(n_ov, "ratio")
        n20 = {"overlap": [config.N20_START, end], "loyo": _clean(n_loyo),
               "coefficients": calib.get("n20_model"),
               "months_used": months.loc[months["source"] == "VIIRS_N20", "ym"].tolist()}

    aq = ov[ov["M_aqua"] >= config.MIN_MODIS_FOR_RATIO]
    aqua = {
        "pearson_r_monthly": _r(np.corrcoef(aq["M_aqua"], aq["V"])[0, 1]),
        "pearson_r_monthly_terra": _r(np.corrcoef(aq["M_terra"], aq["V"])[0, 1]),
        "median_ratio_viirs_over_aqua": _r((aq["V"] / aq["M_aqua"]).median()),
        "median_ratio_viirs_over_terra": _r((aq["V"] / aq["M_terra"].replace(0, np.nan)).median()),
    }

    # invariant check
    con = duckdb.connect()
    det = str(config.PROCESSED / "detections" / f"country={country}" / "**" / "*.parquet")
    w = con.execute(f"""
      SELECT strftime(acq_date, '%Y-%m') ym, sum(harmonized_weight) hw
      FROM read_parquet('{det}', hive_partitioning=true) GROUP BY 1
    """).df().set_index("ym")["hw"]
    chk = months.set_index("ym")["H"].to_frame().join(w).fillna(0)
    max_rel_err = float((abs(chk["H"] - chk["hw"]) / chk["H"].clip(lower=1)).max())

    for col in ("N", "N_cal"):
        if col not in months:
            months[col] = 0.0
    series = months[["ym", "det_M", "det_V", "M", "V", "N", "N_cal", "M_adj", "V_cal", "H", "source",
                     "terra_only", "gap_filled", "partial"]].copy()
    series = series.round(2)

    return {
        "country": country,
        "grid_deg": calib["grid_deg"], "method": method, "overlap": [start, end],
        "loyo": _clean(chosen),
        "loyo_per_year": {str(y): _clean(v) for y, v in chosen["per_year"].items()},
        "candidates": {k: {kk: _r(vv) if isinstance(vv, float) else vv for kk, vv in v.items()}
                       for k, v in calib["selection"].items()},
        "raw_detection_baseline": {
            "loyo": _clean(raw_loyo),
            "annual_ratio_cv": _r(raw_k["k"].std() / raw_k["k"].mean()),
            "celldays_annual_ratio_cv": _r(cd_k["k"].std() / cd_k["k"].mean()),
            "annual_ratio_raw": raw_k[["year", "k"]].round(3).to_dict(orient="records"),
            "annual_ratio_celldays": cd_k[["year", "k"]].round(3).to_dict(orient="records"),
        },
        "sensitivity_overlap_2022": _clean(sens),
        "forward_test_2020_2025": {**_clean(forward), "annual": forward_annual},
        "aqua_vs_snpp": aqua,
        "terra_factor": calib["terra_factor"],
        "coefficients": calib["model"],
        "noaa20": n20,
        "n_months_excluded_outage": int((~clean_month & (months["ym"] >= start) & (months["ym"] <= end)).sum()),
        "outage_months": months.loc[months["gap_filled"], "ym"].tolist(),
        "outage_fill_source": dict(zip(months.loc[months["gap_filled"], "ym"], months.loc[months["gap_filled"], "source"])),
        "invariant_max_rel_err": max_rel_err,
        "series": series.to_dict(orient="records"),
    }


def main(countries: list[str] | None = None) -> None:
    calib = json.loads((config.PROCESSED / "calibration.json").read_text())
    countries = countries or list(calib)
    path = config.PROCESSED / "validation.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    for c in countries:
        v = validate_country(c, calib[c])
        assert v["invariant_max_rel_err"] < 1e-6, f"weight invariant broken: {v['invariant_max_rel_err']}"
        out[c] = v
        l = v["loyo"]
        print(f"{c}: LOYO R2={l['r2']} MAPE={l['mape']}% bias={l['bias_pct']}% annualR2={l['annual_r2']} | "
              f"raw-detection MAPE={v['raw_detection_baseline']['loyo']['mape']}% | "
              f"forward MAPE={v['forward_test_2020_2025']['mape']}% | invariant err={v['invariant_max_rel_err']:.2e}")
    path.write_text(json.dumps(out, default=float))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default=None)
    a = ap.parse_args()
    main(a.countries.split(",") if a.countries else None)
