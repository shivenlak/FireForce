# Data sources (verified 2026-11-14)

## A. FIRMS yearly per-country CSVs (historical, standard processing)
- Index of every file with size + update time: `https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt`
  (the `/country/` listing page is a JS app that reads this file).
- **Per-country CSVs are directly downloadable** — no ZIP streaming needed:
  `https://firms.modaps.eosdis.nasa.gov/data/country/{sensor}/{year}/{sensor}_{year}_{Country}.csv`
  - `sensor`: `modis` (2000–2025), `viirs-snpp` (2012–2025), `viirs-jpss1` (NOAA-20, 2018–2025)
  - Country names use underscores: `United_States`, `Canada`, `Brazil`, `Australia`
  - `{sensor}_{year}_all_countries.zip` also exist (not used).
- Yearly files currently stop at **2025** (2025 files updated 2026-10-10). Everything in 2026 comes from the API.
- Sizes (MB, all years): Canada MODIS 135 / S-NPP 527; Brazil 790 / 1533; Australia 516 / 1370; USA 243 / 571.

### Confirmed fields
- MODIS: `latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type`
  - `satellite` = `Terra`/`Aqua`; `confidence` 0–100; `version` e.g. `6.2`/`61.03`; `type` 0/1/2/3.
  - First Aqua detection in Canada: **2002-07-04**; Terra from 2000-11-01.
- VIIRS S-NPP: `latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight,type`
  - `satellite` = `N`; `confidence` = `l`/`n`/`h`; `version` = 2; `type` 0/2/3 seen. First date 2012-01-20.

## B. FIRMS API
- Key status: `GET /mapserver/mapkey_status/?MAP_KEY=…` → `transaction_limit 5000 / 10 minutes`.
- Availability: `GET /api/data_availability/csv/{KEY}/all` (2026-11-14):

| data_id | min | max |
|---|---|---|
| MODIS_SP | 2000-11-01 | 2026-08-31 |
| MODIS_NRT | 2026-09-01 | 2026-11-14 |
| VIIRS_SNPP_SP | 2012-01-20 | 2026-07-31 |
| VIIRS_SNPP_NRT | 2026-08-01 | **2026-11-02** (feed stops — see QUESTIONS.md) |
| VIIRS_NOAA20_SP / NRT | 2018-04-01 / 2026-08-01 | 2026-07-31 / 2026-11-14 |
| VIIRS_NOAA21_SP / NRT | 2023-03-01 / 2024-01-17 | 2026-07-31 / 2026-11-14 |

- **`/api/country/csv/...` returns `Invalid API call`** for every source/day-range tried. We use the area endpoint instead:
  `/api/area/csv/{KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{YYYY-MM-DD}` — **DAY_RANGE must be 1..5**
  (`Invalid day range. Expects [1..5].`).
- Area results are clipped to the country polygon (Natural Earth, below).
- SP API rows carry `type`; **NRT rows have no `type` column** (MODIS NRT `version` e.g. `6.1NRT`). `acq_time` has no leading zeros.
- Every response is cached under `data/raw/api/{SOURCE}/{bbox-hash}/{start}_{days}.csv`; chunks ending < 3 days ago are cached forever, newer ones for 1 hour. Throttle: 1 request/second.

## C. Country boundaries
- Natural Earth 1:50m admin-0: `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson` (public domain). Used to clip API bbox results, for the country picker and `/api/regions`. A simplified copy of the countries we serve is committed at `data/sample/countries.geojson`.
