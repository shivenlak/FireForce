import datetime as dt

import pandas as pd

RECT = {"type": "Polygon", "coordinates": [[[-121, 49], [-109, 49], [-109, 56], [-121, 56], [-121, 49]]]}
TRI = {"type": "Polygon", "coordinates": [[[-121, 49], [-109, 49], [-121, 56], [-121, 49]]]}


def test_health_and_regions(client):
    h = client.get("/api/health").json()
    assert h["countries"] == ["Testland"]
    assert isinstance(client.get("/api/regions").json(), list)


def test_calendar_shape_and_totals(client):
    r = client.post("/api/calendar", json={"aoi": RECT}).json()
    assert r["years"][0] == 2001 and r["years"][-1] == 2015
    assert len(r["cells"]) == 12 * len(r["years"])
    assert len(r["baseline_median"]) == 12
    by_country = client.post("/api/calendar", json={"country": "Testland"}).json()
    tot = lambda x: sum(c["value"] or 0 for c in x["cells"])  # noqa: E731
    assert abs(tot(r) - tot(by_country)) / tot(by_country) < 1e-9  # AOI covers whole country
    jul = [c for c in r["cells"] if c["year"] == 2001 and c["month"] == 7][0]
    assert "terra_only" in jul["flags"]


def test_polygon_subset_smaller(client):
    full = client.post("/api/calendar", json={"aoi": RECT}).json()
    tri = client.post("/api/calendar", json={"aoi": TRI}).json()
    s = lambda x: sum(c["value"] or 0 for c in x["cells"])  # noqa: E731
    assert 0.2 < s(tri) / s(full) < 0.8


def test_modes_and_date_range(client):
    v = client.post("/api/calendar", json={"aoi": RECT, "mode": "viirs"}).json()
    assert all(c["value"] is None for c in v["cells"] if c["year"] < 2012)
    r = client.post("/api/calendar", json={"aoi": RECT, "start": "2010-01-01", "end": "2010-12-31"}).json()
    assert r["years"] == [2010] and all(c["value"] is not None for c in r["cells"])
    assert r["baseline_median"] == client.post("/api/calendar", json={"aoi": RECT}).json()["baseline_median"]


def test_summary(client):
    s = client.post("/api/summary", json={"aoi": RECT}).json()
    assert s["current"]["year"] == 2015 and 1 <= s["current"]["rank"] <= s["current"]["n_years"]
    assert len(s["climatology"]) == 12 and len(s["peak_months"]) == 3
    assert max(s["peak_months"], key=lambda m: m["value"])["month"] in (6, 7, 8)
    assert set(s["sensor_share"]["detections"]) == {"MODIS", "VIIRS"}


def test_csv_endpoints(client):
    r = client.post("/api/hotspots.csv", json={"aoi": RECT, "start": "2014-07-01", "end": "2014-07-31"})
    assert r.status_code == 200 and r.text.startswith("country,sensor")
    df = pd.read_csv(pd.io.common.StringIO(r.text))
    cal = client.post("/api/calendar", json={"aoi": RECT}).json()
    jul = [c for c in cal["cells"] if c["year"] == 2014 and c["month"] == 7][0]["value"]
    assert abs(df["harmonized_weight"].sum() - jul) < 1e-6
    c = client.post("/api/calendar.csv", json={"country": "Testland"})
    assert c.status_code == 200 and c.text.splitlines()[0].startswith("year,month,value")


def test_points_and_validation(client):
    p = client.post("/api/points", json={"aoi": RECT, "start": "2014-01-01", "end": "2014-12-31"}).json()
    assert p["points"] and len(p["points"][0]) == 4
    v = client.get("/api/validation").json()
    assert "Testland" in v["validation"]


def test_errors(client):
    assert client.post("/api/calendar", json={"country": "Atlantis"}).status_code == 400
    assert client.post("/api/calendar", json={}).status_code == 400
    assert client.post("/api/hotspots.csv", json={}).status_code == 400
    assert client.get("/api/recent?bbox=1,2,3").status_code == 400


def test_recent_uses_cache(client, monkeypatch):
    from pipeline import firms_api

    def fake(src, bbox, start, end, **kw):
        return pd.DataFrame([{"latitude": 50.1, "longitude": -115.2, "acq_date": str(end), "acq_time": "130",
                              "frp": 4.2, "confidence": "n"}])
    monkeypatch.setattr(firms_api, "fetch_range", fake)
    monkeypatch.setattr("pipeline.config.map_key", lambda: "test")
    r = client.get("/api/recent?bbox=-116,49,-114,51&days=3").json()
    assert r["error"] is None and len(r["points"]) == 3 and r["points"][0]["acq_time"] == "0130"
    assert str(dt.date.today().year) in r["points"][0]["acq_date"] or r["points"][0]["acq_date"]
