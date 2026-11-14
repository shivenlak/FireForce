"""API contract. Mirrored by frontend/src/types.ts; change both together."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Mode = Literal["harmonized", "modis", "viirs"]
Flag = Literal["terra_only", "gap_filled", "partial", "no_data"]


class AOIRequest(BaseModel):
    """Area + time selection. Give `aoi` (GeoJSON geometry/Feature) and/or `country`."""
    aoi: Optional[dict[str, Any]] = None
    country: Optional[str] = None
    start: Optional[dt.date] = None
    end: Optional[dt.date] = None
    mode: Mode = "harmonized"
    baseline_start: Optional[int] = None  # first baseline year (default: first complete year)
    baseline_end: Optional[int] = None    # last baseline year (default: last complete year before current)


class Region(BaseModel):
    name: str            # FIRMS file name, e.g. "United_States"
    label: str           # display name
    iso3: str
    bbox: list[float]    # [west, south, east, north]
    has_data: bool


class CalendarCell(BaseModel):
    year: int
    month: int                       # 1..12
    value: Optional[float]           # None = outside data record / selected range
    anomaly_pct: Optional[float]     # (value - median)/median*100; None if median < 1
    zscore: Optional[float]          # robust z = (value - median)/(1.4826*MAD)
    detections: int                  # raw detections behind the value
    source: Optional[Literal["MODIS", "VIIRS", "VIIRS_N20"]]  # harmonized source sensor that month
    flags: list[Flag] = []


class CalendarResponse(BaseModel):
    mode: Mode
    units: str
    years: list[int]
    cells: list[CalendarCell]
    baseline_median: list[Optional[float]]   # 12 values, Jan..Dec
    baseline_years: list[int]                # [first, last]
    countries: list[str]
    data_end: dt.date


class YearValue(BaseModel):
    year: int
    value: float
    partial: bool = False


class MonthValue(BaseModel):
    year: int
    month: int
    value: float


class ClimatologyPoint(BaseModel):
    month: int
    median: Optional[float]
    q25: Optional[float]
    q75: Optional[float]
    current: Optional[float]   # current-year value (None for future months)


class CurrentMonth(BaseModel):
    year: int
    month: int
    day: int                    # month-to-date through this day (last day with data)
    value: float                # month-to-date value this year
    median: Optional[float]     # median month-to-date value in baseline years
    anomaly_pct: Optional[float]
    rank: int                   # 1 = highest of n_years
    n_years: int
    percentile: Optional[float] # % of past years with a lower month-to-date value
    history: list[YearValue]    # month-to-date value in every year


class SensorShare(BaseModel):
    detections: dict[str, int]       # raw detections per sensor in range
    harmonized: dict[str, float]     # share (0..1) of the harmonized total contributed per sensor


class SummaryResponse(BaseModel):
    mode: Mode
    units: str
    current: Optional[CurrentMonth]
    peak_months: list[MonthValue]
    peak_years: list[YearValue]
    annual: list[YearValue]
    climatology: list[ClimatologyPoint]
    sensor_share: SensorShare
    total: float


class PointsResponse(BaseModel):
    """Hotspots aggregated to a display grid: [lat, lon, value, detections]."""
    resolution_deg: float
    points: list[list[float]]
    total_detections: int


class RecentPoint(BaseModel):
    latitude: float
    longitude: float
    acq_date: str
    acq_time: str
    frp: Optional[float]
    confidence: str
    source: str


class RecentResponse(BaseModel):
    bbox: list[float]
    days: int
    fetched_at: str
    sources: list[str]
    points: list[RecentPoint]
    error: Optional[str] = None


class Health(BaseModel):
    data_dir: str
    countries: list[str]
    sample: bool = Field(description="True when serving the small committed sample dataset")
    default_bbox: list[float]   # suggested initial AOI [west, south, east, north]
    default_label: str
    data_end: dt.date
