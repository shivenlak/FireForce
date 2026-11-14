"""Live 'last N days' hotspots from the FIRMS area API (NRT), cached ~1 hour on disk."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from pipeline import config, firms_api

# S-NPP NRT stopped on 2026-11-02 (see QUESTIONS.md), so the live layer uses NOAA-20/21 + MODIS.
RECENT_SOURCES = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT")
MAX_AREA_DEG2 = 2500  # keep requests reasonable (~Alberta+BC sized)


def recent(bbox: list[float], days: int = 7) -> dict:
    w, s, e, n = bbox
    out = {"bbox": bbox, "days": days, "fetched_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "sources": list(RECENT_SOURCES), "points": [], "error": None}
    if not config.map_key():
        out["error"] = "FIRMS_MAP_KEY is not set; live layer unavailable."
        return out
    if (e - w) * (n - s) > MAX_AREA_DEG2:
        out["error"] = f"Area too large for the live layer (max {MAX_AREA_DEG2} square degrees). Zoom in or draw a smaller AOI."
        return out
    today = dt.datetime.utcnow().date()
    start = today - dt.timedelta(days=days - 1)
    frames = []
    try:
        for src in RECENT_SOURCES:
            df = firms_api.fetch_range(src, (round(w, 2), round(s, 2), round(e, 2), round(n, 2)), start, today)
            if len(df):
                frames.append(df.assign(source=src))
    except Exception as ex:  # noqa: BLE001
        out["error"] = f"FIRMS API error: {ex}"
    if frames:
        df = pd.concat(frames, ignore_index=True)
        df["confidence"] = df["confidence"].astype(str)
        df["acq_time"] = df["acq_time"].astype(str).str.zfill(4)
        out["points"] = [
            {"latitude": float(r.latitude), "longitude": float(r.longitude), "acq_date": str(r.acq_date),
             "acq_time": r.acq_time, "frp": None if pd.isna(r.frp) else float(r.frp),
             "confidence": r.confidence, "source": r.source}
            for r in df.itertuples()
        ]
    return out
