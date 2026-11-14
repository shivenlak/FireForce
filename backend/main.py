"""FireCal API. Run: uvicorn backend.main:app --reload"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from backend import firms_client, queries
from backend.schemas import (AOIRequest, CalendarResponse, Health, PointsResponse, RecentResponse,
                             Region, SummaryResponse)

app = FastAPI(title="FireCal API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _run(fn, *args):
    try:
        return fn(queries.store(), *args)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/health", response_model=Health)
def health():
    s = queries.store()
    return {"data_dir": str(s.root), "countries": s.countries, "sample": s.root.name == "sample",
            "default_bbox": s.default["bbox"], "default_label": s.default["label"], "data_end": s.data_end}


@app.get("/api/regions", response_model=list[Region])
def regions():
    return queries.regions(queries.store())


@app.get("/api/regions/{name}/geometry")
def region_geometry(name: str):
    f = queries.region_geometry(queries.store(), name)
    if not f:
        raise HTTPException(404, f"Unknown region {name}")
    return f


@app.post("/api/calendar", response_model=CalendarResponse)
def calendar(req: AOIRequest):
    return _run(queries.calendar, req)


@app.post("/api/summary", response_model=SummaryResponse)
def summary(req: AOIRequest):
    return _run(queries.summary, req)


@app.post("/api/points", response_model=PointsResponse)
def points(req: AOIRequest):
    return _run(queries.points, req)


@app.post("/api/hotspots.csv")
def hotspots_csv(req: AOIRequest):
    gen = queries.hotspots_csv(queries.store(), req)
    try:  # surface validation errors before streaming starts
        first = next(gen)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    def body():
        yield first
        yield from gen
    return StreamingResponse(body(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="firecal_hotspots.csv"'})


@app.post("/api/calendar.csv", response_class=PlainTextResponse)
def calendar_csv(req: AOIRequest):
    text = _run(queries.calendar_csv, req)
    return PlainTextResponse(text, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="firecal_calendar.csv"'})


@app.get("/api/validation")
def validation():
    s = queries.store()
    return {"validation": s.validation, "calibration": {
        c: {k: v for k, v in d.items() if k in ("grid_deg", "method", "overlap", "model", "terra_factor",
                                                "selection", "last_date")}
        for c, d in s.calibration.items()}}


@app.get("/api/recent", response_model=RecentResponse)
def recent(bbox: str = Query(..., description="west,south,east,north"), days: int = Query(7, ge=1, le=10)):
    try:
        b = [float(x) for x in bbox.split(",")]
        assert len(b) == 4 and b[0] < b[2] and b[1] < b[3]
    except (ValueError, AssertionError) as e:
        raise HTTPException(400, "bbox must be 'west,south,east,north'") from e
    return firms_client.recent(b, days)


@app.get("/api/methods", response_class=PlainTextResponse)
def methods():
    """METHODS.md as markdown, rendered on the Methods page."""
    path = queries.ROOT / "METHODS.md"
    return PlainTextResponse(path.read_text() if path.exists() else "", media_type="text/markdown")
