# Open questions for the team

1. **`.env` key format**: the key is stored as `FIRMS_MAP_KEY=<…>` (wrapped in angle brackets). The loader strips `<>`/quotes, so it works, but you may want to remove the brackets.
2. **S-NPP NRT stops at 2026-11-02** in the FIRMS availability table, while NOAA-20/21 NRT run to today. Is S-NPP in safe mode or retired? Done overnight: S-NPP outage months now fall back to **calibrated NOAA-20** (Canada; Brazil/USA/Australia once their NOAA-20 downloads finish), then MODIS. If S-NPP is gone for good, should NOAA-20 become the primary source from Nov 2026?
3. Should NOAA-21 also be calibrated (NRT from 2024, SP from 2023-03) as a third VIIRS fallback?
4. The FIRMS **country API endpoint returns "Invalid API call"** with this key. Maybe it needs a different key tier, or it was retired. The area endpoint works fine.
5. Calibration is per country. Do judges care about sub-national calibration (e.g. 5° tiles)? The weights design supports it.
6. **Brazil: raw detections calibrate slightly better than cell-days** (MAPE 6.9% vs 8.3%), probably because 0.01° cells saturate under big fire fronts (k drops to 2.0 in 2024). Options: a coarser-than-0.01° unit only in Brazil, a saturation-aware model (e.g. log-linear fit per fire-intensity tercile), or accept it. Currently we accept it and say so on the Methods page.
7. Should the overlap window end at 2022 to avoid Terra/Aqua orbit drift? Canada and the USA are insensitive; Brazil improves slightly (MAPE 8.3% → 7.2%).
