PY ?= .venv/bin/python
PYTHON_BOOT ?= $(shell command -v python3.11 || command -v python3.12 || command -v python3.13 || command -v python3)
COUNTRIES ?= Canada
SENSORS ?= modis,viirs-snpp
API_PORT ?= 8010
WEB_PORT ?= 5173

.PHONY: setup data download api-fill build validate sample dev backend frontend test

setup:
	test -d .venv || $(PYTHON_BOOT) -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt
	cd frontend && npm install --no-audit --no-fund

## Full pipeline for COUNTRIES (comma separated FIRMS names, e.g. Canada,Brazil,United_States)
data: download api-fill build validate

download:
	$(PY) -m pipeline.download --countries $(COUNTRIES) --sensors $(SENSORS)
	test -f data/raw/boundaries/ne_50m_admin_0_countries.geojson || (mkdir -p data/raw/boundaries && curl -sL -o data/raw/boundaries/ne_50m_admin_0_countries.geojson https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson)

api-fill:
	$(PY) -m pipeline.firms_api --countries $(COUNTRIES) --sensors $(SENSORS)

build:
	$(PY) -m pipeline.build --countries $(COUNTRIES)

validate:
	$(PY) -m pipeline.validate --countries $(COUNTRIES)

sample:
	$(PY) -m pipeline.sample

## Backend on :$(API_PORT), Vite dev server on :$(WEB_PORT) (proxies /api)
dev:
	@trap 'kill 0' EXIT INT TERM; \
	$(PY) -m uvicorn backend.main:app --port $(API_PORT) --reload --reload-dir backend & \
	cd frontend && API_PORT=$(API_PORT) npx vite --port $(WEB_PORT) & \
	wait

backend:
	$(PY) -m uvicorn backend.main:app --port $(API_PORT) --reload --reload-dir backend

frontend:
	cd frontend && API_PORT=$(API_PORT) npx vite --port $(WEB_PORT)

test:
	$(PY) -m pytest -q
