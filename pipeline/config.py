"""Central configuration for the FireCal pipeline. All tunables live here."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
RAW_YEARLY = RAW / "yearly"
RAW_API = RAW / "api"
LOGS = RAW / "logs"
PROCESSED = DATA / "processed"
SAMPLE = DATA / "sample"

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov"
COUNTRY_INDEX_URL = f"{FIRMS_BASE}/data/country/yearly_summary_files.txt"

# Countries: FIRMS file name -> ISO3 (for the API country endpoint)
COUNTRIES = {
    "Canada": "CAN",
    "Brazil": "BRA",
    "Australia": "AUS",
    "United_States": "USA",
}

# Yearly-file sensor slug -> (sensor family, API SP source, API NRT source)
SENSORS = {
    "modis": ("MODIS", "MODIS_SP", "MODIS_NRT"),
    "viirs-snpp": ("VIIRS", "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"),
    "viirs-jpss1": ("VIIRS_N20", "VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"),
}

# --- Cleaning ---
MODIS_MIN_CONFIDENCE = int(os.getenv("MODIS_MIN_CONFIDENCE", 30))
VIIRS_KEEP_CONFIDENCE = tuple(os.getenv("VIIRS_KEEP_CONFIDENCE", "n,h").split(","))
STATIC_CELL_DEG = 0.01           # grid for static-source mask used on NRT data
STATIC_MIN_MONTHS = 3            # cell flagged static if non-veg (type 2) in >= this many months

# --- Gridding / calibration ---
GRID_CANDIDATES = (0.01, 0.025, 0.05)
GRID_DEG = float(os.getenv("GRID_DEG", 0.025))  # overwritten by calibration choice (see DECISIONS.md)
OVERLAP_START = "2012-02"
OVERLAP_END = os.getenv("OVERLAP_END", "2025-12")  # last complete SP year; see DECISIONS.md
OVERLAP_END_SENSITIVITY = "2022-12"  # pre-drift alternative reported in validation
MIN_MODIS_FOR_RATIO = 20         # skip month-years with fewer MODIS cell-days when fitting ratio
TERRA_ONLY_END = "2002-07"       # Aqua MODIS fire data begins July 2002 in FIRMS
TERRA_FACTOR_YEARS = (2003, 2011)
N20_START = "2018-04"            # NOAA-20 VIIRS standard data start (FIRMS availability)
SWITCH_YEAR = 2012               # MODIS before, calibrated VIIRS from this year on


def map_key() -> str:
    """Read FIRMS_MAP_KEY from .env; tolerate <...>, quotes and whitespace around it."""
    from dotenv import dotenv_values

    key = os.getenv("FIRMS_MAP_KEY") or dotenv_values(ROOT / ".env").get("FIRMS_MAP_KEY") or ""
    return key.strip().strip("<>\"' ")
