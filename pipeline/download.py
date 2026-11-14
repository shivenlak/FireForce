"""Download FIRMS yearly per-country CSVs (historical, standard-processing data).

Usage: python -m pipeline.download --countries Canada,Brazil --sensors modis,viirs-snpp
Resume-safe: files whose size matches the index are skipped. 3 retries per file.
"""
from __future__ import annotations

import argparse
import time

import httpx

from pipeline import config


def fetch_index() -> list[tuple[str, int]]:
    r = httpx.get(config.COUNTRY_INDEX_URL, timeout=60, follow_redirects=True)
    r.raise_for_status()
    rows = []
    for line in r.text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 2 and parts[0].endswith(".csv"):
            rows.append((parts[0], int(parts[1])))
    return rows


def file_url(name: str) -> str:
    sensor, year = name.split("_")[:2]
    return f"{config.FIRMS_BASE}/data/country/{sensor}/{year}/{name}"


def download_file(client: httpx.Client, name: str, size: int) -> str:
    sensor = name.split("_")[0]
    dest = config.RAW_YEARLY / sensor / name
    if dest.exists() and dest.stat().st_size == size:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    for attempt in range(3):
        try:
            with client.stream("GET", file_url(name)) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            tmp.replace(dest)
            return "ok"
        except Exception as e:  # noqa: BLE001
            print(f"  retry {attempt + 1} {name}: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    return "FAILED"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="Canada")
    ap.add_argument("--sensors", default="modis,viirs-snpp")
    args = ap.parse_args()
    index = fetch_index()
    countries = args.countries.split(",")
    sensors = args.sensors.split(",")
    with httpx.Client(timeout=httpx.Timeout(60, read=300), follow_redirects=True) as client:
        for country in countries:
            for sensor in sensors:
                todo = [(n, s) for n, s in index
                        if n.startswith(sensor + "_") and n.endswith(f"_{country}.csv")]
                print(f"{country} {sensor}: {len(todo)} files", flush=True)
                for name, size in sorted(todo):
                    status = download_file(client, name, size)
                    print(f"  {status:6s} {name} ({size / 1e6:.1f} MB)", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
