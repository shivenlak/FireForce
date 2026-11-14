"""Step 3: calibrate VIIRS cell-days to MODIS-equivalent cell-days, per country x month-of-year.

Two candidate models, both fit on the MODIS/VIIRS overlap window:
  ratio : M_hat = V / k_m,          k_m = median_y(V_y,m / M_y,m) over years with M >= MIN
  loglin: log1p(V) = a_m + b_m log1p(M)   (Theil-Sen, robust)  ->  M_hat = expm1((log1p(V)-a)/b)
Months-of-year with too few usable years fall back to a pooled (all-months) fit.
Also estimates the Terra-only -> Terra+Aqua factor f_m for Nov 2000 - Jun 2002.

Functions here are pure pandas so they can be unit-tested on synthetic data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from pipeline import config

MIN_YEARS = 3


def _years(df: pd.DataFrame) -> pd.Series:
    return df["ym"].str[:4].astype(int)


def _moy(df: pd.DataFrame) -> pd.Series:
    return df["ym"].str[5:7].astype(int)


def in_window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return df[(df["ym"] >= start) & (df["ym"] <= end)]


# ---------------------------------------------------------------- ratio model
def fit_ratio(train: pd.DataFrame, min_m: int = config.MIN_MODIS_FOR_RATIO) -> dict:
    ok = train[(train["M"] >= min_m) & (train["V"] > 0)].copy()
    ok["r"] = ok["V"] / ok["M"]
    pooled = float(ok["r"].median()) if len(ok) else 1.0
    coefs = {}
    for m in range(1, 13):
        rs = ok.loc[_moy(ok) == m, "r"]
        if len(rs) >= MIN_YEARS:
            coefs[m] = {"k": float(rs.median()), "n_years": int(len(rs)), "fallback": False,
                        "iqr": [float(rs.quantile(.25)), float(rs.quantile(.75))]}
        else:
            coefs[m] = {"k": pooled, "n_years": int(len(rs)), "fallback": True}
    return {"method": "ratio", "pooled_k": pooled, "months": coefs}


def predict_ratio(model: dict, df: pd.DataFrame) -> np.ndarray:
    k = _moy(df).map(lambda m: model["months"][m]["k"]).to_numpy()
    return df["V"].to_numpy() / k


# ---------------------------------------------------------------- log-linear model
def _theil(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    b, a, _, _ = stats.theilslopes(y, x)
    return float(a), float(max(b, 0.2))  # guard against degenerate slopes


def fit_loglin(train: pd.DataFrame, min_m: int = config.MIN_MODIS_FOR_RATIO) -> dict:
    ok = train[(train["M"] >= min_m) & (train["V"] > 0)]
    x, y = np.log1p(ok["M"].to_numpy()), np.log1p(ok["V"].to_numpy())
    pa, pb = _theil(x, y) if len(ok) >= 3 else (0.0, 1.0)
    coefs = {}
    for m in range(1, 13):
        sub = ok[_moy(ok) == m]
        if len(sub) >= 6 and np.ptp(np.log1p(sub["M"])) > 0.5:
            a, b = _theil(np.log1p(sub["M"].to_numpy()), np.log1p(sub["V"].to_numpy()))
            coefs[m] = {"a": a, "b": b, "n_years": int(len(sub)), "fallback": False}
        else:
            coefs[m] = {"a": pa, "b": pb, "n_years": int(len(sub)), "fallback": True}
    return {"method": "loglin", "pooled": {"a": pa, "b": pb}, "months": coefs}


def predict_loglin(model: dict, df: pd.DataFrame) -> np.ndarray:
    a = _moy(df).map(lambda m: model["months"][m]["a"]).to_numpy()
    b = _moy(df).map(lambda m: model["months"][m]["b"]).to_numpy()
    out = np.expm1((np.log1p(df["V"].to_numpy()) - a) / b)
    return np.clip(out, 0, None)


FITS = {"ratio": (fit_ratio, predict_ratio), "loglin": (fit_loglin, predict_loglin)}


def predict(model: dict, df: pd.DataFrame) -> np.ndarray:
    return FITS[model["method"]][1](model, df)


# ---------------------------------------------------------------- metrics + LOYO
def metrics(obs: np.ndarray, pred: np.ndarray, min_obs: int = config.MIN_MODIS_FOR_RATIO) -> dict:
    obs, pred = np.asarray(obs, float), np.asarray(pred, float)
    ss_res = float(((obs - pred) ** 2).sum())
    ss_tot = float(((obs - obs.mean()) ** 2).sum()) or np.nan
    mask = obs >= min_obs
    mape = float(np.mean(np.abs(pred[mask] - obs[mask]) / obs[mask]) * 100) if mask.any() else None
    mdape = float(np.median(np.abs(pred[mask] - obs[mask]) / obs[mask]) * 100) if mask.any() else None
    bias = float((pred.sum() - obs.sum()) / obs.sum() * 100) if obs.sum() else None
    return {"r2": float(1 - ss_res / ss_tot), "mape": mape, "median_ape": mdape,
            "bias_pct": bias, "n_months": int(len(obs)), "n_months_mape": int(mask.sum())}


def loyo(overlap: pd.DataFrame, method: str) -> tuple[dict, pd.DataFrame]:
    """Leave-one-year-out: fit on all other overlap years, predict held-out year's MODIS."""
    fit, pred = FITS[method]
    years = sorted(_years(overlap).unique())
    rows = []
    per_year = {}
    for y in years:
        test = overlap[_years(overlap) == y]
        model = fit(overlap[_years(overlap) != y])
        p = pred(model, test)
        rows.append(test.assign(pred=p))
        per_year[int(y)] = metrics(test["M"].to_numpy(), p)
    res = pd.concat(rows)
    annual = res.groupby(_years(res))[["M", "pred"]].sum()
    out = metrics(res["M"].to_numpy(), res["pred"].to_numpy())
    out["annual_r2"] = metrics(annual["M"].to_numpy(), annual["pred"].to_numpy())["r2"]
    out["per_year"] = per_year
    return out, res


def annual_k(monthly: pd.DataFrame) -> pd.DataFrame:
    """Per-year aggregate V/M ratio and Terra/Aqua balance: used to choose the overlap window."""
    y = monthly.assign(year=_years(monthly)).groupby("year")[["M", "V", "M_terra", "M_aqua"]].sum()
    y["k"] = y["V"] / y["M"].replace(0, np.nan)
    y["terra_over_aqua"] = y["M_terra"] / y["M_aqua"].replace(0, np.nan)
    return y.reset_index()


# ---------------------------------------------------------------- Terra-only factor
def terra_factor(monthly: pd.DataFrame, years=config.TERRA_FACTOR_YEARS,
                 min_m: int = config.MIN_MODIS_FOR_RATIO) -> dict:
    yr = _years(monthly)
    sub = monthly[(yr >= years[0]) & (yr <= years[1]) & (monthly["M_terra"] >= min_m)]
    r = sub["M"] / sub["M_terra"]
    pooled = float(r.median()) if len(r) else 1.0
    out = {}
    for m in range(1, 13):
        rm = r[_moy(sub) == m]
        out[m] = float(rm.median()) if len(rm) >= MIN_YEARS else pooled
    return {"pooled": pooled, "months": out, "years": list(years)}
