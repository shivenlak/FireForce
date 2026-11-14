"""Step 2: common grid and the 'fire cell-day' unit.

A fire cell-day is a distinct (grid cell, UTC date) pair with >= 1 detection from a sensor family.
Counting cell-days instead of detections removes VIIRS's resolution inflation (375 m vs 1 km
pixels) and the double counting from multiple overpasses per day.
"""
from __future__ import annotations


def cell_expr(g: float, lat: str = "latitude", lon: str = "longitude") -> str:
    """SQL expression for an int64 cell id on a g-degree grid (row * 100000 + col)."""
    return (f"(floor(({lat} + 90) / {g})::BIGINT * 100000 + "
            f"floor(({lon} + 180) / {g})::BIGINT)")


def cell_center(cell_id: int, g: float) -> tuple[float, float]:
    row, col = divmod(int(cell_id), 100000)
    return (row + 0.5) * g - 90, (col + 0.5) * g - 180


def monthly_celldays_sql(src: str, g: float) -> str:
    """Monthly cell-days per sensor family, plus Terra-only and Aqua-only MODIS cell-days."""
    c = cell_expr(g)
    return f"""
      WITH d AS (SELECT sensor, satellite, acq_date, {c} AS cell FROM {src})
      SELECT strftime(acq_date, '%Y-%m') AS ym,
             count(DISTINCT CASE WHEN sensor='MODIS' THEN (cell, acq_date) END) AS M,
             count(DISTINCT CASE WHEN sensor='MODIS' AND satellite='Terra' THEN (cell, acq_date) END) AS M_terra,
             count(DISTINCT CASE WHEN sensor='MODIS' AND satellite='Aqua' THEN (cell, acq_date) END) AS M_aqua,
             count(DISTINCT CASE WHEN sensor='VIIRS' THEN (cell, acq_date) END) AS V,
             count(DISTINCT CASE WHEN sensor='VIIRS_N20' THEN (cell, acq_date) END) AS N,
             count(*) FILTER (WHERE sensor='MODIS') AS det_M,
             count(*) FILTER (WHERE sensor='VIIRS') AS det_V,
             count(*) FILTER (WHERE sensor='VIIRS_N20') AS det_N
      FROM d GROUP BY 1 ORDER BY 1
    """
