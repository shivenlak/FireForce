"""Step 1: clean + unify MODIS and VIIRS detections for one country.

Output: data/processed/clean/{country}.parquet with a unified schema:
  country, sensor (MODIS|VIIRS), satellite, latitude, longitude, acq_date, acq_time,
  confidence (raw string), daynight, frp, type (NULL for NRT), source (SP|NRT)

Rules (identical for both sensors, thresholds in config.py):
  * type == 0 only (where type exists); NRT rows have no type, so we drop NRT detections in
    0.01-degree cells that are persistent static sources in the SP record.
  * MODIS confidence >= MODIS_MIN_CONFIDENCE; VIIRS confidence in VIIRS_KEEP_CONFIDENCE.
  * API (bbox) rows are clipped to the country polygon.
  * Dedupe on (sensor, satellite, lat, lon, acq_date, acq_time); SP wins over NRT.
"""
from __future__ import annotations

import argparse
import datetime as dt

import duckdb

from pipeline import config

FAMILIES = (("modis", "MODIS"), ("viirs-snpp", "VIIRS"), ("viirs-jpss1", "VIIRS_N20"))
BOUNDARIES = config.RAW / "boundaries" / "ne_50m_admin_0_countries.geojson"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    return con


def _sensor_select(path_glob: str, family: str, source: str, has_type: bool) -> str:
    type_expr = "TRY_CAST(type AS INTEGER)" if has_type else "NULL::INTEGER"
    return f"""
      SELECT '{family}' AS sensor,
             CAST(satellite AS VARCHAR) AS satellite,
             CAST(latitude AS DOUBLE) AS latitude, CAST(longitude AS DOUBLE) AS longitude,
             CAST(acq_date AS DATE) AS acq_date, CAST(acq_time AS INTEGER) AS acq_time,
             lower(CAST(confidence AS VARCHAR)) AS confidence,
             CAST(daynight AS VARCHAR) AS daynight, CAST(frp AS DOUBLE) AS frp,
             {type_expr} AS type, '{source}' AS source
      FROM read_csv('{path_glob}', header=true, union_by_name=true, all_varchar=true)
    """


def _conf_filter() -> str:
    keep = ",".join(f"'{c}'" for c in config.VIIRS_KEEP_CONFIDENCE)
    return f"""(
      (sensor = 'MODIS' AND TRY_CAST(confidence AS INTEGER) >= {config.MODIS_MIN_CONFIDENCE})
      OR (sensor LIKE 'VIIRS%' AND left(confidence, 1) IN ({keep}))
    )"""


def clean_country(country: str, con: duckdb.DuckDBPyConnection | None = None) -> dict:
    con = con or connect()
    out_dir = config.PROCESSED / "clean"
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for slug, family in FAMILIES:
        files = sorted((config.RAW_YEARLY / slug).glob(f"{slug}_*_{country}.csv"))
        if files:
            parts.append(_sensor_select(str(config.RAW_YEARLY / slug / f"{slug}_*_{country}.csv"),
                                        family, "SP", True))
    con.execute(f"CREATE OR REPLACE TEMP TABLE sp AS {' UNION ALL '.join(parts)}")

    # Static-source mask from SP: 0.01-deg cells with non-vegetation type in >= N distinct months
    g = config.STATIC_CELL_DEG
    con.execute(f"""
      CREATE OR REPLACE TEMP TABLE static_cells AS
      SELECT floor(latitude/{g})::BIGINT AS r, floor(longitude/{g})::BIGINT AS c
      FROM sp WHERE type IN (1, 2)
      GROUP BY 1, 2 HAVING count(DISTINCT date_trunc('month', acq_date)) >= {config.STATIC_MIN_MONTHS}
    """)

    # API rows (current year; SP + NRT mixed, 'source' column already present)
    api_parts = []
    for slug, family in FAMILIES:
        for f in sorted((config.RAW_API / "merged").glob(f"{slug}_*_{country}.csv")):
            if f.stat().st_size < 200:
                continue
            cols = con.execute(f"SELECT * FROM read_csv('{f}', all_varchar=true) LIMIT 0").description
            names = [c[0] for c in cols]
            has_type = "type" in names
            sel = _sensor_select(str(f), family, "X", has_type).replace("'X' AS source", "source")
            api_parts.append(sel)
    if api_parts:
        con.execute(f"CREATE OR REPLACE TEMP TABLE api_raw AS {' UNION ALL '.join(api_parts)}")
        iso = config.COUNTRIES[country]
        con.execute(f"""
          CREATE OR REPLACE TEMP TABLE boundary AS
          SELECT geom FROM ST_Read('{BOUNDARIES}') WHERE ADM0_A3 = '{iso}'
        """)
        con.execute("""
          CREATE OR REPLACE TEMP TABLE api AS
          SELECT a.* FROM api_raw a, boundary b
          WHERE ST_Contains(b.geom, ST_Point(a.longitude, a.latitude))
        """)
        # Drop NRT detections in static cells (no `type` field in NRT)
        con.execute(f"""
          DELETE FROM api WHERE type IS NULL AND (floor(latitude/{g})::BIGINT, floor(longitude/{g})::BIGINT)
            IN (SELECT (r, c) FROM static_cells)
        """)
        union = "SELECT * FROM sp UNION ALL SELECT * FROM api"
    else:
        union = "SELECT * FROM sp"

    out = out_dir / f"{country}.parquet"
    con.execute(f"""
      COPY (
        SELECT '{country}' AS country, * EXCLUDE (rn) FROM (
          SELECT *, row_number() OVER (
            PARTITION BY sensor, satellite, round(latitude, 4), round(longitude, 4), acq_date, acq_time
            ORDER BY CASE source WHEN 'SP' THEN 0 ELSE 1 END) AS rn
          FROM ({union})
          WHERE (type = 0 OR type IS NULL) AND {_conf_filter()}
        ) WHERE rn = 1
        ORDER BY acq_date
      ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
    """)
    # Daily raw detection counts (all types/confidences) per sensor: used to find sensor outages.
    # Canada/USA/etc. have gas flares and industry every day, so a zero-detection day is a data gap.
    raw_union = "SELECT sensor, acq_date FROM sp" + (" UNION ALL SELECT sensor, acq_date FROM api" if api_parts else "")
    con.execute(f"""
      COPY (SELECT sensor, acq_date, count(*) AS n_all FROM ({raw_union}) GROUP BY ALL ORDER BY ALL)
      TO '{out_dir / f"{country}_daily_raw.parquet"}' (FORMAT parquet)
    """)
    stats = con.execute(f"""
      SELECT sensor, source, count(*) n, min(acq_date) first, max(acq_date) last
      FROM '{out}' GROUP BY ALL ORDER BY ALL
    """).fetchall()
    raw_n = con.execute("SELECT count(*) FROM sp").fetchall()[0][0]
    n_static = con.execute("SELECT count(*) FROM static_cells").fetchall()[0][0]
    print(f"{country}: raw SP rows {raw_n:,}, static cells {n_static:,}")
    for s in stats:
        print("  ", s)
    return {"country": country, "raw_sp_rows": raw_n, "static_cells": n_static,
            "built": dt.datetime.now().isoformat(timespec="seconds")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="Canada")
    a = ap.parse_args()
    for c in a.countries.split(","):
        clean_country(c)
