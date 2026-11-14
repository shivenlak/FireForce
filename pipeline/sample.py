"""Write the small committed sample dataset (data/sample/) from data/processed/.

The sample covers one 3x3-degree box in British Columbia (Kelowna-Kamloops, fire-prone Okanagan)
with every cleaned detection and its weights, plus Canada's monthly flags, calibration and
validation, so the frontend runs without the multi-GB download.
Usage: python -m pipeline.sample
"""
from __future__ import annotations

import json
import shutil

import duckdb

from pipeline import config

SAMPLE_COUNTRY = "Canada"
SAMPLE_BBOX = [-121.5, 49.0, -118.5, 52.0]  # west, south, east, north


def main() -> None:
    src, dst = config.PROCESSED, config.SAMPLE
    det_dst = dst / "detections"
    if det_dst.exists():
        shutil.rmtree(det_dst)
    w, s, e, n = SAMPLE_BBOX
    con = duckdb.connect()
    con.execute(f"""
      COPY (SELECT * FROM read_parquet('{src}/detections/country={SAMPLE_COUNTRY}/**/*.parquet', hive_partitioning=true)
            WHERE latitude BETWEEN {s} AND {n} AND longitude BETWEEN {w} AND {e})
      TO '{det_dst}' (FORMAT parquet, PARTITION_BY (country, sensor), COMPRESSION zstd)
    """)
    (dst / "months").mkdir(parents=True, exist_ok=True)
    shutil.copy(src / "months" / f"{SAMPLE_COUNTRY}.parquet", dst / "months" / f"{SAMPLE_COUNTRY}.parquet")
    for name in ("calibration.json", "validation.json"):
        d = json.loads((src / name).read_text())
        (dst / name).write_text(json.dumps({SAMPLE_COUNTRY: d[SAMPLE_COUNTRY]}, default=float))
    (dst / "sample.json").write_text(json.dumps({"country": SAMPLE_COUNTRY, "bbox": SAMPLE_BBOX,
                                                 "label": "Kelowna-Kamloops, British Columbia"}))
    print("sample written:", sum(p.stat().st_size for p in dst.rglob("*") if p.is_file()) / 1e6, "MB")


if __name__ == "__main__":
    main()
