"""FIRMS area API client with on-disk caching and throttling.

Verified 2026-11-14: the /api/country/ endpoint returns "Invalid API call" for our key,
so we use /api/area/ with country bounding boxes (max DAY_RANGE = 5) and clip to the
country polygon afterwards (see clean.py).

Usage: python -m pipeline.firms_api --countries Canada --sensors modis,viirs-snpp
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import time

import httpx
import pandas as pd

from pipeline import config

MAX_DAYS = 5
_last_call = 0.0

# Bounding boxes (west, south, east, north) covering each country; several for the USA.
COUNTRY_BBOXES = {
    "Canada": [(-141.1, 41.6, -52.5, 83.2)],
    "Brazil": [(-74.1, -33.8, -34.7, 5.4)],
    "Australia": [(112.8, -43.7, 153.7, -10.6)],
    "United_States": [(-125.0, 24.4, -66.8, 49.5), (-170.0, 51.0, -129.9, 71.5),
                      (-160.3, 18.8, -154.7, 22.3)],
}


def _get(url: str, retries: int = 5) -> str:
    global _last_call
    for attempt in range(retries):
        wait = 1.0 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
        try:
            r = httpx.get(url, timeout=180)
            text = r.text
            if r.status_code == 200 and text.startswith("latitude"):
                return text
            if "exceed" in text.lower():  # "Exceeding allowed transaction limit" (5000 / 10 min window)
                print("  transaction limit hit; waiting 5 min", flush=True)
                time.sleep(300)
                continue
            elif text.strip() == "" and r.status_code == 200:
                return ""
            print(f"  API error ({r.status_code}): {text[:120]}", flush=True)
        except httpx.HTTPError as e:
            print(f"  API exception: {e}", flush=True)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"FIRMS API failed after {retries} attempts")


def availability() -> dict[str, tuple[str, str]]:
    text = _get_cached_availability()
    df = pd.read_csv(io.StringIO(text))
    return {r.data_id: (r.min_date, r.max_date) for r in df.itertuples()}


def _get_cached_availability() -> str:
    path = config.RAW_API / "data_availability.csv"
    if path.exists() and time.time() - path.stat().st_mtime < 3600:
        return path.read_text()
    url = f"{config.FIRMS_BASE}/api/data_availability/csv/{config.map_key()}/all"
    r = httpx.get(url, timeout=60)
    r.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(r.text)
    return r.text


def fetch_area(source: str, bbox: tuple, start: dt.date, days: int,
               max_age_s: float | None = None) -> pd.DataFrame:
    """Fetch one <=5-day chunk, cached on disk. max_age_s=None means cache forever."""
    bkey = hashlib.md5(",".join(f"{v:.2f}" for v in bbox).encode()).hexdigest()[:8]
    path = config.RAW_API / source / bkey / f"{start.isoformat()}_{days}.csv"
    if path.exists() and (max_age_s is None or time.time() - path.stat().st_mtime < max_age_s):
        text = path.read_text()
    else:
        b = ",".join(str(v) for v in bbox)
        url = f"{config.FIRMS_BASE}/api/area/csv/{config.map_key()}/{source}/{b}/{days}/{start.isoformat()}"
        text = _get(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(text), dtype={"acq_time": str, "confidence": str, "version": str})


def fetch_range(source: str, bbox: tuple, start: dt.date, end: dt.date,
                recent_max_age_s: float = 3600) -> pd.DataFrame:
    frames = []
    today = dt.date.today()
    d = start
    while d <= end:
        days = min(MAX_DAYS, (end - d).days + 1)
        chunk_end = d + dt.timedelta(days=days - 1)
        age = recent_max_age_s if (today - chunk_end).days < 3 else None
        df = fetch_area(source, bbox, d, days, max_age_s=age)
        if len(df):
            frames.append(df)
        d = chunk_end + dt.timedelta(days=1)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fill_recent(country: str, sensor: str, start: dt.date | None = None) -> pd.DataFrame:
    """Fetch everything after the last yearly file: SP while available, then NRT."""
    _, sp, nrt = config.SENSORS[sensor]
    avail = availability()
    start = start or dt.date(dt.date.today().year, 1, 1)
    today = dt.date.today()
    sp_end = min(dt.date.fromisoformat(avail[sp][1]), today) if sp in avail else start - dt.timedelta(days=1)
    nrt_end = dt.date.fromisoformat(avail[nrt][1]) if nrt in avail else today
    frames = []
    for bbox in COUNTRY_BBOXES[country]:
        if sp_end >= start:
            df = fetch_range(sp, bbox, start, sp_end)
            if len(df):
                df["source"] = "SP"
                frames.append(df)
        nrt_start = max(start, sp_end + dt.timedelta(days=1))
        if nrt_end >= nrt_start:
            df = fetch_range(nrt, bbox, nrt_start, min(nrt_end, today))
            if len(df):
                df["source"] = "NRT"
                frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    print(f"{country} {sensor}: {len(out)} API rows (SP to {sp_end}, NRT to {nrt_end})", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="Canada")
    ap.add_argument("--sensors", default="modis,viirs-snpp")
    args = ap.parse_args()
    for country in args.countries.split(","):
        for sensor in args.sensors.split(","):
            df = fill_recent(country, sensor)
            out = config.RAW_API / "merged" / f"{sensor}_{dt.date.today().year}_{country}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out, index=False)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
