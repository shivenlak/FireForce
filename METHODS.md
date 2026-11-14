# Methods: harmonizing MODIS and VIIRS active-fire detections

**Goal:** one hotspot time series from Nov 2000 to today in which the sensor no longer matters.
Units are **MODIS-equivalent fire cell-days**.

## 1. Clean (same rules for both sensors)
- Keep `type = 0` (presumed vegetation fire). Drop volcanoes (1), static land sources such as gas flares and industry (2), and offshore detections (3).
- Near-real-time (NRT) rows have no `type`, so we drop NRT detections that fall in 0.01° cells which are persistent static sources in the standard (SP) record, meaning type 1/2 detections in ≥3 distinct months.
- Confidence: MODIS ≥ 30; VIIRS nominal + high (low dropped). Both thresholds are configurable.
- Day and night detections are both kept. Duplicates between SP and NRT are removed, preferring SP.

## 2. Common unit: fire cell-days
A VIIRS 375 m pixel is ~1/7 the area of a MODIS 1 km pixel, so one fire produces many more VIIRS detections, and each satellite overpasses a different number of times per day. Raw counts are therefore not comparable.
We snap every detection to a regular lat/lon grid and count **distinct (grid cell, UTC date) pairs per sensor family**. This removes both the resolution inflation and the multiple-overpass double counting.
We tested 0.01°, 0.025° and 0.05° grids (see §5).

## 3. Calibrate VIIRS to MODIS
- **Overlap:** Feb 2012 – Dec 2025 (S-NPP starts 20 Jan 2012; the 2025 yearly files are the last complete standard-processing year). In Canada the Terra/Aqua cell-day balance stays within its historical range through 2025, so orbit drift is not yet visible in the counts.
- **Model (per country × month-of-year m):** `k_m = median over overlap years of V/M`, using only months with ≥20 MODIS cell-days. A month with fewer than 3 usable years falls back to the pooled ratio.
  Harmonized VIIRS: `M̂ = V / k_m`.
  We also tested a robust log-linear model, `log1p(V) = a_m + b_m·log1p(M)` (Theil–Sen). It validated worse (bias +6–8%), so we use the ratio model.
- **Harmonized series:** MODIS for Nov 2000 – Jan 2012, calibrated VIIRS from Feb 2012 onward. This single switchover keeps the series running after MODIS ends.
- **Per-detection weights**, so any area of interest (AOI) can be summed. Let `n` = number of detections of that sensor in the same cell-day.
  - MODIS: `f_m / n`, where f_m is the Terra-only factor (§4) and 1 otherwise.
  - VIIRS: `(1/k_m) / n`.
  - `harmonized_weight` is that value when the detection's sensor is the month's harmonized source, and 0 otherwise.
  - Summing `harmonized_weight` over an AOI gives its harmonized cell-days. At country level this reproduces the series exactly (max relative error 5×10⁻¹³).

## 4. Consistency traps
- **Terra-only era (Nov 2000 – Jun 2002).** Aqua MODIS starts 4 Jul 2002, so early counts are biased low. We estimate `f_m = median(all-MODIS / Terra-only cell-days)` per month-of-year over 2003–2011, apply it to the Terra-only months, and flag them in the calendar. For Canada, f ranges from 1.35 in July to about 2 in winter.
- **Overpass time.** S-NPP crosses at ~13:30 local, like Aqua. Monthly S-NPP cell-days correlate with Aqua-only cell-days at r = 0.979 (Canada).
- **Sensor outages.** An outage day is one with zero S-NPP detections of any type while MODIS has ≥5. Months with ≥2 outage days use MODIS (flagged "gap-filled"). This catches the S-NPP safe-mode event of 27 Jul – 10 Aug 2022, the 2024 gaps, and the end of the S-NPP NRT feed on 2 Nov 2026.
- **Partial current month.** Flagged in the calendar. The "this month vs history" card compares month-to-date against the same day range in every past year.

## 5. Validation (Canada)
Leave-one-year-out (LOYO): for each overlap year, fit on all other years, predict that year's monthly MODIS cell-days from VIIRS, and score.

| Test | R² (monthly) | MAPE | Bias | Annual R² |
|---|---|---|---|---|
| **Chosen: 0.01°, ratio, LOYO 2012–2025** | **0.968** | **18.0%** | **−2.9%** | **0.976** |
| Same model on raw detection counts (no cell-days) | 0.931 | 21.9% | +8.6% | 0.918 |
| Overlap ending 2022 (sensitivity) | 0.942 | 20.4% | −2.1% | 0.860 |
| Forward test: fit 2012–2019, predict 2020–2025 | 0.971 | 20.2% | −6.1% | – |

MAPE is computed over months with ≥20 MODIS cell-days. The year-to-year coefficient of variation of the VIIRS/MODIS ratio is 0.13 for cell-days versus 0.18 for raw detections: the cell-day unit is more stable.
Full candidate table (3 grids × 2 models), per-year scores and monthly series: `data/processed/validation.json`, also shown on the app's Methods page.

## 6. Analytics definitions
- **Calendar cell:** harmonized fire cell-days for (year, month) in the AOI.
- **Baseline:** per-month median over complete years excluding the current one.
- **Anomaly:** `(value − median)/median` in percent. Undefined (shown as "—") when the median is below 1 cell-day. Also a robust z-score `(value − median) / (1.4826·MAD)`.
- **Month-to-date:** days 1..today of the current month compared with days 1..today of the same month in every past year, with rank and percentile.

## 7. Limitations
- Calibration is per country, not per AOI. Small AOIs with an unusual fire regime (e.g. many small agricultural fires) inherit the country ratio.
- One cell-day is not one fire; it's an index of burning activity, not burned area.
- Terra and Aqua orbits are drifting. If the 2026 MODIS counts drop further, the overlap window should end at 2022 (sensitivity above).
- NRT (2026) uses a static mask instead of the `type` field. Dedupe between NRT and SP may leave a small number of near-duplicates.
