import json

import duckdb
import numpy as np
import pandas as pd

from pipeline import calibrate as cal


def _synthetic_monthly(k=2.0, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for y in range(2012, 2024):
        for m in range(1, 13):
            M = float(50 + 500 * np.exp(-((m - 7) ** 2) / 3) * rng.uniform(0.5, 2))
            V = M * k * (1 + noise * rng.normal())
            rows.append({"ym": f"{y}-{m:02d}", "M": M, "V": V, "M_terra": M / 1.5, "M_aqua": M / 1.5})
    return pd.DataFrame(rows)


def test_ratio_recovers_known_k():
    model = cal.fit_ratio(_synthetic_monthly(k=2.3))
    assert all(abs(v["k"] - 2.3) < 1e-9 for v in model["months"].values())


def test_loyo_perfect_and_noisy():
    perfect, _ = cal.loyo(_synthetic_monthly(k=3.0), "ratio")
    assert perfect["mape"] < 1e-6 and perfect["r2"] > 0.999
    noisy, _ = cal.loyo(_synthetic_monthly(k=3.0, noise=0.1), "ratio")
    assert 1 < noisy["mape"] < 20


def test_loglin_identity():
    model = cal.fit_loglin(_synthetic_monthly(k=1.0))
    df = _synthetic_monthly(k=1.0)
    assert np.allclose(cal.predict(model, df), df["M"], rtol=0.05)


def test_ratio_fallback_when_modis_tiny():
    df = _synthetic_monthly(k=2.0)
    df.loc[df["ym"].str.endswith("-01"), ["M", "V"]] = [1.0, 5.0]  # January never usable
    model = cal.fit_ratio(df)
    assert model["months"][1]["fallback"] and abs(model["months"][1]["k"] - 2.0) < 1e-9


def test_metrics_handles_zero_obs():
    m = cal.metrics(np.array([0, 0, 100.0]), np.array([1, 0, 110.0]))
    assert m["n_months_mape"] == 1 and abs(m["mape"] - 10) < 1e-9


def test_pipeline_outputs(built):
    calib = json.loads((built / "calibration.json").read_text())["Testland"]
    assert calib["grid_deg"] in (0.01, 0.025, 0.05)
    months = pd.read_parquet(built / "months" / "Testland.parquet")
    assert months["terra_only"].any() and (months.loc[months["ym"] < "2002-07", "terra_only"]).all()
    assert set(months.loc[months["ym"] >= "2012-02", "source"]) == {"VIIRS"}
    # Terra-only factor should be ~ (1 - 0.3^2)/0.7 = 1.3 for the synthetic 70% detection prob
    assert 1.1 < calib["terra_factor"]["pooled"] < 1.6


def test_static_sources_removed(built):
    n = duckdb.sql(f"SELECT count(*) FROM '{built}/clean/Testland.parquet' "
                   "WHERE latitude = 51.0 AND longitude = -115.0").fetchall()[0][0]
    assert n == 0


def test_weight_invariant_and_validation(built):
    v = json.loads((built / "validation.json").read_text())["Testland"]
    assert v["invariant_max_rel_err"] < 1e-9
    assert v["loyo"]["r2"] > 0.8
    # harmonized VIIRS-era annual totals ~ MODIS-era level (same synthetic fire regime)
    s = pd.DataFrame(v["series"])
    s["year"] = s["ym"].str[:4].astype(int)
    a = s.groupby("year")["H"].sum()
    assert 0.6 < a.loc[2012:2015].mean() / a.loc[2003:2011].mean() < 1.6
