// Mirrors backend/schemas.py. Change both together.

export type Mode = "harmonized" | "modis" | "viirs";
export type Flag = "terra_only" | "gap_filled" | "partial" | "no_data";
export type Geometry = { type: string; coordinates: unknown };

export interface AOIRequest {
  aoi?: Geometry | null;
  country?: string | null;
  start?: string | null; // YYYY-MM-DD
  end?: string | null;
  mode: Mode;
  baseline_start?: number | null;
  baseline_end?: number | null;
}

export interface Region {
  name: string;
  label: string;
  iso3: string;
  bbox: [number, number, number, number];
  has_data: boolean;
}

export interface CalendarCell {
  year: number;
  month: number;
  value: number | null;
  anomaly_pct: number | null;
  zscore: number | null;
  detections: number;
  source: "MODIS" | "VIIRS" | "VIIRS_N20" | null;
  flags: Flag[];
}

export interface CalendarResponse {
  mode: Mode;
  units: string;
  years: number[];
  cells: CalendarCell[];
  baseline_median: (number | null)[];
  baseline_years: number[];
  countries: string[];
  data_end: string;
}

export interface YearValue { year: number; value: number; partial: boolean }
export interface MonthValue { year: number; month: number; value: number }
export interface ClimatologyPoint {
  month: number;
  median: number | null;
  q25: number | null;
  q75: number | null;
  current: number | null;
}
export interface CurrentMonth {
  year: number;
  month: number;
  day: number;
  value: number;
  median: number | null;
  anomaly_pct: number | null;
  rank: number;
  n_years: number;
  percentile: number | null;
  history: YearValue[];
}
export interface SensorShare {
  detections: Record<string, number>;
  harmonized: Record<string, number>;
}
export interface SummaryResponse {
  mode: Mode;
  units: string;
  current: CurrentMonth | null;
  peak_months: MonthValue[];
  peak_years: YearValue[];
  annual: YearValue[];
  climatology: ClimatologyPoint[];
  sensor_share: SensorShare;
  total: number;
}

export interface PointsResponse {
  resolution_deg: number;
  points: [number, number, number, number][]; // lat, lon, value, detections
  total_detections: number;
}

export interface RecentPoint {
  latitude: number;
  longitude: number;
  acq_date: string;
  acq_time: string;
  frp: number | null;
  confidence: string;
  source: string;
}
export interface RecentResponse {
  bbox: number[];
  days: number;
  fetched_at: string;
  sources: string[];
  points: RecentPoint[];
  error: string | null;
}

export interface Health {
  data_dir: string;
  countries: string[];
  sample: boolean;
  default_bbox: [number, number, number, number];
  default_label: string;
  data_end: string;
}

// /api/validation is a loose JSON document (see pipeline/validate.py)
export interface Metrics {
  r2: number;
  mape: number | null;
  median_ape?: number | null;
  bias_pct: number | null;
  annual_r2?: number | null;
  n_months: number;
  score?: number;
  k_cv?: number;
}
export interface SeriesRow {
  ym: string;
  det_M: number;
  det_V: number;
  M: number;
  V: number;
  M_adj: number;
  V_cal: number;
  H: number;
  source: string;
  terra_only: boolean;
  gap_filled: boolean;
  partial: boolean;
}
export interface CountryValidation {
  country: string;
  grid_deg: number;
  method: string;
  overlap: [string, string];
  loyo: Metrics;
  loyo_per_year: Record<string, Metrics>;
  candidates: Record<string, Metrics>;
  raw_detection_baseline: {
    loyo: Metrics;
    annual_ratio_cv: number;
    celldays_annual_ratio_cv: number;
    annual_ratio_raw: { year: number; k: number }[];
    annual_ratio_celldays: { year: number; k: number }[];
  };
  sensitivity_overlap_2022: Metrics;
  forward_test_2020_2025: Metrics & { annual: { year: string; M: number; pred: number }[] };
  aqua_vs_snpp: Record<string, number>;
  terra_factor: { pooled: number; months: Record<string, number> };
  coefficients: { method: string; months: Record<string, { k?: number; a?: number; b?: number; n_years: number; fallback: boolean }> };
  noaa20: { overlap: [string, string]; loyo: Metrics; coefficients: { months: Record<string, { k: number }> }; months_used: string[] } | null;
  outage_months: string[];
  outage_fill_source: Record<string, string>;
  invariant_max_rel_err: number;
  series: SeriesRow[];
}
export interface ValidationResponse {
  validation: Record<string, CountryValidation>;
  calibration: Record<string, unknown>;
}
