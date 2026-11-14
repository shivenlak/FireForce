import L from "leaflet";
import "leaflet-draw";
import { useEffect, useMemo } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { AOI } from "../aoi";
import { aoiGeometry } from "../aoi";
import { INFERNO_R, fmt, interp } from "../colors";
import type { PointsResponse, RecentResponse } from "../types";

interface Props {
  aoi: AOI;
  bbox: [number, number, number, number] | null;
  countryFeature: GeoJSON.Feature | null;
  points: PointsResponse | null;
  recent: RecentResponse | null;
  onDraw: (a: AOI) => void;
}

export default function MapView({ aoi, bbox, countryFeature, points, recent, onDraw }: Props) {
  const outline = useMemo(() => {
    if (aoi.kind === "country") return countryFeature;
    const g = aoiGeometry(aoi);
    return g ? ({ type: "Feature", properties: {}, geometry: g } as GeoJSON.Feature) : null;
  }, [aoi, countryFeature]);
  const vmax = useMemo(() => Math.max(1, ...(points?.points.map((p) => p[2]) ?? [1])), [points]);

  return (
    <MapContainer
      className="map"
      center={[52, -110]}
      zoom={4}
      preferCanvas
      worldCopyJump
      aria-label="Map of hotspots. Use the draw tools at the top left to select an area."
    >
      <TileLayer
        attribution="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        maxZoom={16}
      />
      <FitBounds bbox={bbox} />
      <DrawControl onDraw={onDraw} />
      {outline && (
        <GeoJSON
          key={JSON.stringify(outline.geometry).slice(0, 200)}
          data={outline}
          style={{ color: "#0072B2", weight: 2, fillOpacity: 0.04, dashArray: "6 4" }}
          interactive={false}
        />
      )}
      {points?.points.map(([lat, lon, v, n], i) => (
        <CircleMarker
          key={`${lat},${lon},${i}`}
          center={[lat, lon]}
          radius={Math.max(2, Math.min(9, 2 + Math.log10(1 + v) * 2))}
          pathOptions={{
            stroke: false,
            fillColor: interp(INFERNO_R.slice(2), Math.log10(1 + v) / Math.log10(1 + vmax)),
            fillOpacity: 0.85,
          }}
        >
          <Tooltip>{fmt(v, 1)} cell-days · {n.toLocaleString()} detections</Tooltip>
        </CircleMarker>
      ))}
      {recent?.points.map((p, i) => (
        <CircleMarker
          key={`r${i}`}
          center={[p.latitude, p.longitude]}
          radius={4}
          pathOptions={{ color: "#00a3d9", weight: 2, fillColor: "#fff", fillOpacity: 0.9 }}
        >
          <Tooltip>
            Live {p.source.replace("_NRT", "")} · {p.acq_date} {p.acq_time} UTC · FRP {fmt(p.frp, 1)} MW
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}

function FitBounds({ bbox }: { bbox: [number, number, number, number] | null }) {
  const map = useMap();
  const key = bbox?.join(",");
  useEffect(() => {
    if (!bbox) return;
    const [w, s, e, n] = bbox;
    map.fitBounds([[s, w], [n, e]], { padding: [20, 20], maxZoom: 10 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

function DrawControl({ onDraw }: { onDraw: (a: AOI) => void }) {
  const map = useMap();
  useEffect(() => {
    const control = new L.Control.Draw({
      position: "topleft",
      draw: {
        rectangle: { shapeOptions: { color: "#0072B2" } },
        polygon: { allowIntersection: false, shapeOptions: { color: "#0072B2" } },
        circle: false, circlemarker: false, marker: false, polyline: false,
      },
    });
    map.addControl(control);
    const onCreated = (e: L.LeafletEvent) => {
      const ev = e as L.DrawEvents.Created;
      const layer = ev.layer as L.Polygon;
      const latlngs = (layer.getLatLngs()[0] as L.LatLng[]).map((p) => [p.lng, p.lat] as [number, number]);
      if (ev.layerType === "rectangle") {
        const b = layer.getBounds();
        onDraw({ kind: "bbox", bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => +v.toFixed(4)) as [number, number, number, number] });
      } else {
        onDraw({ kind: "polygon", ring: latlngs.map(([x, y]) => [+x.toFixed(4), +y.toFixed(4)]) });
      }
    };
    map.on(L.Draw.Event.CREATED, onCreated);
    return () => {
      map.off(L.Draw.Event.CREATED, onCreated);
      map.removeControl(control);
    };
  }, [map, onDraw]);
  return null;
}
