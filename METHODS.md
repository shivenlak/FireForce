# Methods: harmonizing MODIS and VIIRS active-fire detections

**Goal:** one hotspot time series from Nov 2000 to today in which the sensor no longer matters.
Units are **MODIS-equivalent fire cell-days**.

## 1. Clean (same rules for every sensor)
- Keep `type = 0` (presumed vegetation fire). Drop volcanoes (1), static land sources such as gas flares and industry (2), and offshore detections (3).
- Near-real-time (NRT) rows have no `type`, so we drop NRT detections that fall in 0.01° cells which are persistent static sources in the standard (SP) record, meaning type 1/2 detections in ≥3 distinct months.
- Confidence: MODIS ≥ 30; VIIRS nominal + high (low dropped). Both thresholds are configurable.
- Day and night detections are both kept. SP/NRT duplicates are removed, preferring SP. API (bounding-box) results are clipped to the country polygon.

## 2. Common unit: fire cell-days
A VIIRS 375 m pixel covers about 1/7 the area of a MODIS 1 km pixel, so one fire produces many more VIIRS detections, and each satellite overpasses a different number of times per day. Raw counts are therefore not comparable.
We snap every detection to a regular lat/lon grid and count **distinct (grid cell, UTC date) pairs per sensor**. This removes both the resolution inflation and the multiple-overpass double counting.
0.01°, 0.025° and 0.05° grids were tested (§5). The grid is chosen per country: **0.01° for Canada, Brazil and the USA; 0.025° for Australia.**

## 3. Calibrate VIIRS to MODIS
- **Overlap:** Feb 2012 – Dec 2025. S-NPP starts 20 Jan 2012; 2025 is the last complete standard-processing year. **Months with any sensor-outage day are excluded** from fitting and validation (9–11 months per country), because a partial VIIRS month biases the ratio.
- **Model (per country × month-of-year m):** `k_m = median over overlap years of V/M`, using months with ≥20 MODIS cell-days; a month with fewer than 3 usable years falls back to the pooled ratio. Harmonized VIIRS: `M̂ = V / k_m`.
  A robust log-linear alternative, `log1p(V) = a_m + b_m·log1p(M)` (Theil–Sen), is also fitted. The model with the lower LOYO score (MAPE + |bias|) is used: **ratio for Canada, Brazil and the USA; log-linear for Australia**, where it captures the slight saturation in big fire years (score 7.7 vs 9.6). With the log-linear model, a detection's VIIRS weight uses the country-month scale `M̂/V`.
- **Seasonality matters:** in Canada k ranges from 2.0 (May/Oct) to 5.6 (Mar). VIIRS's advantage is largest when fires are small.
- **NOAA-20 (VIIRS on JPSS-1):** calibrated to MODIS with the ratio model over Apr 2018 – Dec 2025. LOYO R² / MAPE: Canada 0.987 / 17.5%, Brazil 0.983 / 9.7%, USA 0.949 / 10.7%, Australia 0.943 / 11.5%. It fills 44 of the 47 S-NPP outage months across the four countries.
- **Harmonized series:** MODIS for Nov 2000 – Jan 2012. From Feb 2012 the source is a monthly cascade: **calibrated S-NPP → calibrated NOAA-20 (if S-NPP has an outage) → MODIS (if NOAA-20 is unavailable too).** Every source is in MODIS-equivalent units, so the series keeps running after MODIS ends.
- **Per-detection weights**, so any area of interest (AOI) can be summed. Let `n` = number of detections of that sensor in the same cell-day.
  - MODIS: `f_m / n`, where f_m is the Terra-only factor (§4) and 1 otherwise.
  - S-NPP: `(1/k_m) / n`.
  - NOAA-20: `(1/k^N20_m) / n`.
  - `harmonized_weight` is that value when the detection's sensor is the month's harmonized source, and 0 otherwise.
  - Summing `harmonized_weight` over any AOI gives its harmonized cell-days. At country level this reproduces the series to within 10⁻¹² (checked on every build).

## 4. Consistency traps
- **Terra-only era (Nov 2000 – Jun 2002).** Aqua MODIS starts 4 Jul 2002, so early counts are biased low. We estimate `f_m = median(all-MODIS / Terra-only cell-days)` per month-of-year over 2003–2011, apply it to the Terra-only months, and hatch them in the calendar. Pooled f: Canada 2.03, USA 2.17, Australia 2.21, Brazil 2.62. Aqua's afternoon overpass sees many fires Terra's morning pass misses; in Brazil this is the strongest.
- **Overpass time.** S-NPP crosses at ~13:30 local, like Aqua. Monthly S-NPP cell-days correlate with Aqua-only cell-days at r = 0.981 (Canada), 0.990 (Brazil), 0.953 (USA), 0.985 (Australia).
- **Sensor outages.** An outage day is one with zero S-NPP (or NOAA-20) detections of any type while MODIS has ≥5. Gas flares make every normal day non-zero. Days after a feed's last date also count. A month with ≥2 outage days uses the next source in the cascade and is hatched "gap-filled". This catches the S-NPP safe-mode event of 27 Jul – 10 Aug 2022, gaps in 2024, and the end of the S-NPP NRT feed on 2 Nov 2026.
- **Partial current month.** Flagged in the calendar. The "this month vs history" card compares month-to-date against the same day range in every past year.

## 5. Validation
Leave-one-year-out (LOYO): for each overlap year, fit on all other years, predict that year's monthly MODIS cell-days from VIIRS, and score. MAPE uses months with ≥20 MODIS cell-days.

| Country | LOYO R² | MAPE | Bias | Annual R² | Same model on raw detections (MAPE / bias) | Forward test 2020–25 (fit 2012–19) | Overlap ending 2022 (MAPE) |
|---|---|---|---|---|---|---|---|
| Canada | **0.972** | **18.4%** | −1.7% | 0.972 | 21.8% / +10.8% | 21.1% | 20.3% |
| Brazil | **0.991** | **8.3%** | −1.2% | 0.953 | 6.9% / +0.3% | 11.1% | 7.2% |
| United States | **0.954** | **9.9%** | −0.4% | 0.874 | 10.7% / +2.4% | 12.8% | 9.7% |
| Australia (0.025°, log-linear) | **0.985** | **7.5%** | +0.1% | 0.990 | 7.5% / +0.9% | 9.6% | 8.4% |

(`python -m pipeline.report` prints the current table.)

What this shows:
- Calibrated VIIRS reproduces MODIS month by month with R² ≥ 0.95 and bias within ±2% in all four countries. "Raw lines disagree, harmonized lines overlap": see the Methods page chart.
- **Cell-days vs raw detections.** In Canada (many small fires) cell-days are clearly better: the year-to-year CV of the ratio is 0.13 vs 0.18, and bias is −1.7% vs +10.8%. In the USA they are slightly better; in Australia they tie. **In Brazil raw detections do slightly better** (CV 0.04 vs 0.06). There, very large, dense fire fronts saturate 0.01° cells in extreme years (the ratio drops to 2.0 in the record 2024 season). We keep one unit everywhere so AOIs spanning countries stay consistent; a per-region unit choice is listed in QUESTIONS.md.
- The forward test (training only on pre-2020 years) shows the calibration transfers to unseen years, including Canada's record 2023 season.
- Grid/model candidates, per-year errors, k by month and the full monthly series are in `data/processed/validation.json` and on the Methods page.

## 6. Analytics definitions
- **Calendar cell:** harmonized fire cell-days for (year, month) in the AOI.
- **Baseline:** per-month median over complete years excluding the current one (default 2001–2025).
- **Anomaly:** `(value − median)/median` in percent. Undefined ("—") when the median is below 1 cell-day. Also a robust z-score `(value − median) / (1.4826·MAD)`. The anomaly colors use log₂(value/median), clamped to ⅛×…8×, so "half" and "double" look equally strong.
- **Month-to-date:** days 1..today of the current month vs the same days in every past year, with rank and percentile.

## 7. Limitations
- Calibration is per country. A small AOI with an unusual fire regime inherits the country's monthly ratio.
- A cell-day is an index of burning activity, not a count of fires or burned area.
- Terra and Aqua orbits are drifting. In Brazil, an overlap ending in 2022 validates slightly better than one ending in 2025; this should be revisited as more MODIS data arrive.
- NRT months (2026) use a static-source mask instead of the `type` field; new flares since 2025 may leak in.
- Only S-NPP and NOAA-20 are calibrated. NOAA-21 (2023–) could be added the same way.
