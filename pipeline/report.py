"""Print the per-country validation summary as a Markdown table (for METHODS.md / slides).

Usage: python -m pipeline.report
"""
from __future__ import annotations

import json

from pipeline import config


def fmt(v, pct=False):
    if v is None:
        return "–"
    return f"{v:+.1f}%" if pct == "signed" else (f"{v:.1f}%" if pct else f"{v:.3f}")


def main() -> None:
    v = json.loads((config.PROCESSED / "validation.json").read_text())
    print("| Country | Grid · model | LOYO R² | MAPE | Bias | Annual R² | Raw-detection MAPE | Forward MAPE | NOAA-20 LOYO R² / MAPE | Outage months filled |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for c, d in v.items():
        l, raw, fw = d["loyo"], d["raw_detection_baseline"]["loyo"], d["forward_test_2020_2025"]
        n = d.get("noaa20")
        n20 = f"{fmt(n['loyo']['r2'])} / {fmt(n['loyo']['mape'], True)}" if n else "–"
        fills = d.get("outage_fill_source", {})
        nf = sum(1 for s in fills.values() if s == "VIIRS_N20")
        print(f"| {c.replace('_', ' ')} | {d['grid_deg']}° · {d['method']} | {fmt(l['r2'])} | {fmt(l['mape'], True)} | "
              f"{fmt(l['bias_pct'], 'signed')} | {fmt(l['annual_r2'])} | {fmt(raw['mape'], True)} | {fmt(fw['mape'], True)} | "
              f"{n20} | {len(fills)} ({nf} NOAA-20) |")


if __name__ == "__main__":
    main()
