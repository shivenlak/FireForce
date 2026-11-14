# Handoff (written end of overnight run, 2026-11-14)

## What's done
- **Pipeline** (`pipeline/`): FIRMS yearly per-country CSV download, 2026 API fill (SP then NRT, area endpoint + polygon clip), cleaning, cell-day gridding, grid/model selection by LOYO, Terra-only correction, outage detection + MODIS gap-fill, per-detection weights, validation, and the sample-data builder.
- **Countries processed:** see PROGRESS.md. Canada is complete and validated.
- **Backend** (`backend/`): every endpoint in the spec plus `/api/points` (map aggregation), `/api/methods` and `/api/health`. 17 pytest tests run the real pipeline on a synthetic country.
- **Frontend** (`frontend/`): map + AOI tools, calendar (counts/anomaly, flags, numbers, PNG, table view), analytics cards, annual + climatology charts, Methods & Validation page, CSV downloads, live layer, URL state. Playwright smoke test in `frontend/e2e/smoke.mjs`.

## Half-done / known issues
- **AOI calibration is country-level.** A small AOI inherits the country's monthly k. Fine for the MVP; a judge may ask about it.
- **S-NPP NRT stopped on 2026-11-02.** Recent months are gap-filled from MODIS. MODIS is near end of life, so NOAA-20 calibration is the real fix (QUESTIONS.md #2).
- **NRT static-source mask** covers only cells seen in SP data. New flares since 2025 may leak into 2026 NRT months.
- **The FIRMS `/api/country/` endpoint is rejected** for our key; we use bbox + polygon clip instead.
- **Map points** are aggregated to an adaptive grid (max 6000 cells), so individual detections aren't shown; the CSV has them.
- **The live layer is unfiltered** (includes gas flares) and is capped at 2500 square degrees.
- **AOIs across the antimeridian** (Aleutians) are not handled.
- The ECharts heatmap is canvas, so the `<details>` table is the accessible fallback. A proper keyboard-navigable grid would be better.
- `make dev` uses port 8010 for the API (8000 was taken on this machine). Override with `make dev API_PORT=...`.

## Proposed branch split
The contract between the two branches is **`backend/schemas.py` ↔ `frontend/src/types.ts`**. Change both in the same PR, and tell the other branch.

### Branch A: data/science (`feat/science`)
Owns: `pipeline/`, `backend/queries.py`, `backend/main.py`, `backend/firms_client.py`, `tests/`, `METHODS.md`, `DATA_SOURCES.md`, `DECISIONS.md`, `data/sample/` (regenerate with `make sample`).
Top 5:
1. **NOAA-20 calibration** (`viirs-jpss1` files are already listed in the index): calibrate N20 → MODIS on 2018–2025 and use it for S-NPP outage months instead of MODIS; then make N20 the primary source for 2026+.
2. **Sub-national calibration**: fit k on 5° tiles with ≥N overlap months and fall back to the country. The weights design supports this already: just make `viirs_scale` depend on (tile, month).
3. **AOI-specific calibration on the fly** (stretch): when the AOI has enough overlap data, fit k for the AOI and report it next to the country k.
4. **Uncertainty bands**: bootstrap k over overlap years and propagate to a per-cell interval (show it in the tooltip).
5. **Pipeline robustness**: refresh the 2026 NRT cache daily (cron), make the static mask also learn from recent NRT, and add more countries (the pipeline takes any FIRMS country name).

### Branch B: product/UX (`feat/ux`)
Owns: `frontend/` (everything), `docs/screenshots/`, `README.md`.
Top 5:
1. **Demo polish**: a guided "story" preset (e.g. the 2023 Canada season, or Kelowna 2003/2023), plus a hero first-load view.
2. **Calendar interaction**: click a cell to filter the map to that month; brush-select years; a keyboard-navigable grid.
3. **Map**: choropleth/heat toggle, a legend for map points, and a cluster view at low zoom.
4. **Exports**: a one-page PDF report for the AOI (calendar + cards + methods blurb), and shareable-link copy.
5. **Mobile layout + accessibility audit** (axe), plus a dark mode.

## How to run
`make setup && make dev`, then open http://localhost:5173. With no processed data, the app uses `data/sample/`.
