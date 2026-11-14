# Decisions log

Decisions made unattended; each is easy to revisit (most are one line in `pipeline/config.py`).

1. **Python 3.11 venv** (`/opt/homebrew/bin/python3.11`); system python is 3.9.
2. **Direct per-country CSV downloads** instead of ZIPs (URL pattern verified, see DATA_SOURCES.md).
3. **API area endpoint + polygon clip** for 2026, because the country endpoint returns "Invalid API call". USA uses 3 bboxes (CONUS, Alaska, Hawaii; Aleutians west of 180° skipped).
4. **2026 data = SP from the API while available, NRT after** (MODIS SP to 08-31, S-NPP SP to 07-31). Dedupe key `(sensor, satellite, lat, lon rounded 1e-4, date, time)`, SP preferred.
5. **Static-source mask for NRT**: 0.01° cells with type 1/2 detections in ≥3 distinct months of the SP record (Canada: 259 cells, mostly Alberta/BC gas flares).
6. **Cleaning**: type==0; MODIS confidence ≥30; VIIRS `n`,`h`. Day + night kept.
7. **Overlap window 2012-02 → 2025-12.** S-NPP starts 2012-01-20 (Jan 2012 incomplete). The Terra/Aqua cell-day ratio in Canada stays within its 2003–2022 year-to-year range through 2025 (0.94–1.09 at 0.05°) and only drops in 2026 (0.87, partial year), so orbit drift isn't yet visible in the counts. Including 2023 (the record season) also tests the calibration in an extreme year. Sensitivity run with 2012–2022 is reported in validation (LOYO MAPE 20.4% vs 18.0%).
8. **Grid = 0.01°, model = ratio** (Canada). Chosen by LOYO score = monthly MAPE + |bias|. All three grids have similar MAPE (17.8–18.3%), but 0.05° under-predicts big fire years (bias −7.9%) because coarse cells saturate; 0.01° has bias −2.9% and annual R² 0.976. Ratio beat log-linear at every grid (log-linear had +6–8% bias). Grid/model are chosen per country and stored in `calibration.json`.
9. **Selection score includes |bias|** rather than MAPE alone: for a 25-year trend tool, a systematic bias is worse than slightly noisier months.
10. **Switchover month 2012-02** (MODIS before, calibrated VIIRS from then on).
11. **Outage gap-filling**: a VIIRS "outage day" = 0 raw S-NPP detections (any type/confidence) while MODIS has ≥5; also every day after the feed's last date. Months with ≥2 outage days use MODIS for the harmonized value (flagged `gap_filled`). Canada: 2022-07/08 (the known S-NPP safe-mode event, 27 Jul–10 Aug 2022), 2024-05/06/07/11, 2026-04/06/07/11. MODIS outages need VIIRS ≥200 that day, because VIIRS routinely sees ~10–60 small flares on days MODIS sees nothing.
12. **Terra-only correction** (2000-11 → 2002-06): multiply by month-of-year factor f_m = median(all-MODIS / Terra-only cell-days) over 2003–2011 (Canada at 0.01°: pooled 2.03, monthly range 1.67–2.32). Those cells are flagged in the UI. July 2002 (Aqua from the 4th) is treated as Terra+Aqua.
13. **Per-detection weights**: `cellday_weight = 1/n_det(cell-day)`, `calibrated_weight` = MODIS-equivalent weight (MODIS: terra_factor/n; VIIRS: (V_cal/V)/n = (1/k_m)/n), `harmonized_weight` = calibrated weight if the detection's sensor is that month's harmonized source, else 0. Summing `harmonized_weight` over any AOI gives the harmonized count; verified exactly at country level (max rel. error 5e-13).
14. **Calibration is country-level** and applied to any AOI inside that country. An AOI-specific fit is a stretch goal.
15. **Backend reads `data/processed/` if it has detections, else `data/sample/`** (env `DATA_DIR` overrides).
16. **Outage months excluded from calibration and validation.** Any month with ≥1 outage day for S-NPP or MODIS (NOAA-20 or MODIS for the N20 fit) is left out of the fit. This improved Brazil's annual R² from 0.89 to 0.95.
17. **NOAA-20 cascade.** In the VIIRS era the harmonized source is S-NPP; if S-NPP has ≥2 outage days, calibrated NOAA-20; if NOAA-20 is unavailable too, MODIS. NOAA-20 is calibrated to MODIS with the same ratio model over 2018-04 → 2025-12.
18. **One unit (cell-days) for every country**, even though raw detections validate slightly better in Brazil. Mixing units would break AOIs that span countries and make the UI confusing. Revisit with a saturation-aware model (QUESTIONS.md).
19. **One global overlap window (2012-02 → 2025-12).** Brazil validates slightly better ending in 2022. Comparing LOYO scores across different windows isn't apples to apples, so we report the sensitivity instead of tuning per country.
20. **API port 8010** (8000 was in use by another process on this machine).
21. **Backend store reloads automatically** when `calibration.json` changes, so a running dev server picks up new pipeline output.
