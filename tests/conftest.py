"""Builds a tiny synthetic FIRMS dataset ('Testland') and runs the real pipeline on it."""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd
import pytest

from pipeline import config

TRUE_K = 2.5  # VIIRS produces ~2.5x the MODIS cell-days in the synthetic world


def _write_year(raw, year, rng):
    modis, viirs = [], []
    for month in range(1, 13):
        n_fires = int(20 + 200 * np.exp(-((month - 7) ** 2) / 4) * rng.uniform(0.5, 1.5))
        ndays = pd.Period(f"{year}-{month:02d}").days_in_month
        for _ in range(n_fires):
            lat, lon = rng.uniform(50, 55), rng.uniform(-120, -110)
            day = dt.date(year, month, int(rng.integers(1, ndays + 1)))
            sats = ["Terra"] if (year, month) < (2002, 7) else ["Terra", "Aqua"]
            for sat in sats:
                if rng.random() < 0.7:
                    modis.append((lat, lon, day, 1030 if sat == "Terra" else 1330, sat, 80, 0))
            if year >= 2012:
                # VIIRS: each fire is seen in ~TRUE_K distinct 0.01-deg cells, several pixels each
                for j in range(int(round(TRUE_K * 0.7 * 2))):
                    for _ in range(3):
                        viirs.append((lat + 0.012 * j, lon, day, 1330, "N", "n", 0))
        # a daily gas flare (type 2) so every day has raw detections
        for d in range(1, ndays + 1):
            modis.append((51.0, -115.0, dt.date(year, month, d), 1030, "Terra", 90, 2))
            if year >= 2012:
                viirs.append((51.0, -115.0, dt.date(year, month, d), 1330, "N", "h", 2))
    cols = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "type"]
    m = pd.DataFrame(modis, columns=cols).assign(brightness=320, scan=1, track=1, instrument="MODIS",
                                                 version="6.1", bright_t31=290, frp=10.0, daynight="D")
    (raw / "modis").mkdir(parents=True, exist_ok=True)
    m.to_csv(raw / "modis" / f"modis_{year}_Testland.csv", index=False)
    if viirs:
        v = pd.DataFrame(viirs, columns=cols).assign(bright_ti4=330, scan=0.4, track=0.4, instrument="VIIRS",
                                                     version="2", bright_ti5=290, frp=3.0, daynight="D")
        (raw / "viirs-snpp").mkdir(parents=True, exist_ok=True)
        v.to_csv(raw / "viirs-snpp" / f"viirs-snpp_{year}_Testland.csv", index=False)


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("firecal")
    rng = np.random.default_rng(42)
    raw, processed = root / "raw", root / "processed"
    for y in range(2001, 2016):
        _write_year(raw / "yearly", y, rng)
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "RAW", raw)
    mp.setattr(config, "RAW_YEARLY", raw / "yearly")
    mp.setattr(config, "RAW_API", raw / "api")
    mp.setattr(config, "PROCESSED", processed)
    mp.setattr(config, "OVERLAP_END", "2015-12")
    mp.setattr(config, "OVERLAP_END_SENSITIVITY", "2014-12")
    from pipeline import build, validate
    build.build_country("Testland")
    validate.main(["Testland"])
    yield processed
    mp.undo()


@pytest.fixture(scope="session")
def client(built):
    os.environ["DATA_DIR"] = str(built)
    from fastapi.testclient import TestClient

    from backend import queries
    from backend.main import app
    queries.store.cache_clear()
    yield TestClient(app)
    queries.store.cache_clear()
    del os.environ["DATA_DIR"]
