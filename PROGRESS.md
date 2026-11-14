# Progress log (overnight run, 2026-11-14)

## Milestones
| | Status | Notes |
|---|---|---|
| M0 setup + discovery | ✅ | Key, data availability and URL pattern verified (DATA_SOURCES.md). The country API endpoint is rejected, so we use the area endpoint. |
| M1 ingest | ✅ | Canada: MODIS 2000–2025, S-NPP 2012–2025, NOAA-20 2018–2025 yearly files; 2026 from the API (SP then NRT). |
| M2 harmonize + validate | ✅ | Cell-days, 3 grids × 2 models by LOYO, Terra-only factor, outage detection, weights, validation.json. |
| M3 backend | ✅ | All endpoints + `/api/points`, `/api/methods`, `/api/health`. 17 pytest tests. |
| M4 frontend MVP | ✅ | Map, AOI draw/point/country, calendar, CSV downloads; Playwright smoke test + screenshots. |
| M5 analytics | ✅ | Anomaly %, robust z, month-to-date rank/percentile, climatology, annual totals, peaks, sensor share, mode toggle, flags. |
| M6 more countries | ✅ | Brazil, USA, Australia processed and validated. |
| M7 live data | ✅ | `/api/recent` (NOAA-20/21 + MODIS NRT, 1 h cache) + map layer. |
| M8 polish | ✅ | README, HANDOFF, METHODS with real numbers, aria labels, keyboard focus, table view, PNG export. |
| Stretch: NOAA-20 gap filling | ✅ | Calibrated NOAA-20 replaces S-NPP in outage months in all 4 countries (LOYO R² 0.94–0.99); 44 of 47 outage months filled from NOAA-20. |
| Stretch: PNG export | ✅ | ECharts "Save PNG" on the calendar. |
| Stretch: AOI-specific calibration, PDF report | ❌ | Not started (see HANDOFF next tasks). |

## Validation (LOYO, 2012–2025)
| Country | R² | MAPE | Bias | Annual R² |
|---|---|---|---|---|
| Canada | 0.972 | 18.4% | −1.7% | 0.972 |
| Brazil | 0.991 | 8.3% | −1.2% | 0.953 |
| USA | 0.954 | 9.9% | −0.4% | 0.874 |
| Australia | 0.985 | 7.5% | +0.1% | 0.990 |

## Things that went wrong, and what I did
- **FIRMS country API returned "Invalid API call"** → switched to the area endpoint (max 5 days per call) + polygon clip.
- **`.env` key wrapped in `<…>`** → the loader strips it.
- **CARTO basemap now requires an API key** → switched to Esri World Light Gray.
- **ECharts heatmaps require `visualMap`** (crashed the page) → color index mapped through a hidden piecewise visualMap.
- **Rectangle fast-path bug** (a triangle with the same corners was treated as a rectangle) → caught by a test, fixed.
- **FIRMS transaction limit hit** during parallel API fills ("Exceeding allowed transaction limit") → backoff now waits 5 min; the failed NOAA-20 fill was re-run.
- **Port 8000 is used by another process on this machine** → API runs on 8010.
- **Per-connection download throttling** → ran per-country downloads in parallel.
- **Brazil: raw detections validate slightly better than cell-days**. Reported honestly; options in QUESTIONS.md #6.

## Final state
- All 4 countries processed (MODIS + S-NPP + NOAA-20, 2000-11 → 2026-11-14), validated, and served from `data/processed/`. Tables: `python -m pipeline.report`.
- No background jobs left running except the dev servers (`make dev`, ports 8010/5173) I used for testing. Stop them with Ctrl-C or `pkill -f "uvicorn backend.main:app --port 8010"; pkill -f vite`.
- `make test`: 17 passed. Playwright smoke test: 8 screenshots in `docs/screenshots/`, no console errors.
- Fresh clone → `make setup` → backend serves `data/sample/` correctly (verified).
