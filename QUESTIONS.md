# Open questions for the team

1. **`.env` key format**: the key is stored as `FIRMS_MAP_KEY=<…>` (wrapped in angle brackets). The loader strips `<>`/quotes, so it works, but you may want to remove the brackets.
2. **S-NPP NRT stops at 2026-11-02** in the FIRMS availability table, while NOAA-20/21 NRT run to today. Is S-NPP in safe mode or retired? Right now we fill Nov 2026 from MODIS (flagged). If S-NPP is gone for good, we should calibrate NOAA-20 → MODIS-equivalent and switch to it (stretch goal, pipeline ready for `viirs-jpss1`).
3. Should the harmonized series switch to NOAA-20 for months where S-NPP is down instead of MODIS? MODIS is nearing end of life, so this matters for the future.
4. The FIRMS **country API endpoint returns "Invalid API call"** with this key. Maybe it needs a different key tier, or it was retired. The area endpoint works fine.
5. Calibration is per country. Do judges care about sub-national calibration (e.g. 5° tiles)? The weights design supports it.
