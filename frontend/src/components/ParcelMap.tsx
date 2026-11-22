import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { GeoJsonGeometry } from "../api/types";
import type { Place } from "../lib/geocoder";

// Orthophoto of GUGiK (public WMTS, key-value requests, tile grid EPSG:3857).
const ORTHOPHOTO =
  "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMTS/StandardResolution" +
  "?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTOFOTOMAPA&STYLE=default" +
  "&FORMAT=image/jpeg&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}&TILEROW={y}&TILECOL={x}";
const ATTRIBUTION = "Ortofotomapa: GUGiK (geoportal.gov.pl)";

// Extent of the orthophoto layer as its service describes it; no tiles are asked outside.
const COVERAGE: L.LatLngBoundsLiteral = [
  [48.8, 13.8],
  [55.0, 24.4],
];
const POLAND_CENTER: L.LatLngTuple = [52.07, 19.48];
const POLAND_ZOOM = 6;
const OUTLINE: L.PathOptions = { color: "#ffffff", weight: 3, fillColor: "#2F7FE0", fillOpacity: 0.25 };

interface Props {
  geometry: GeoJsonGeometry | null;
  place: Place | null;
  caption: string;
  onPick: (lat: number, lon: number) => void;
}

/** Map of Poland: a click picks the parcel under it, the picked parcel is outlined. */
export function ParcelMap({ geometry, place, caption, onPick }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const outline = useRef<L.GeoJSON | null>(null);
  const pick = useRef(onPick);
  pick.current = onPick;

  useEffect(() => {
    if (!container.current) return;
    const created = L.map(container.current, {
      zoomControl: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
    }).setView(POLAND_CENTER, POLAND_ZOOM);
    L.tileLayer(ORTHOPHOTO, { maxZoom: 19, attribution: ATTRIBUTION, bounds: COVERAGE }).addTo(created);
    created.on("click", (event: L.LeafletMouseEvent) => pick.current(event.latlng.lat, event.latlng.lng));
    map.current = created;
    return () => {
      created.remove();
      map.current = null;
      outline.current = null;
    };
  }, []);

  useEffect(() => {
    const current = map.current;
    if (!current) return;
    outline.current?.remove();
    outline.current = null;
    if (!geometry) return;
    const layer = L.geoJSON(geometry as GeoJSON.GeoJsonObject, { style: OUTLINE, interactive: false });
    layer.addTo(current);
    outline.current = layer;
    current.fitBounds(layer.getBounds(), { padding: [60, 60], maxZoom: 18 });
  }, [geometry]);

  useEffect(() => {
    if (!place) return;
    if (place.bounds) map.current?.fitBounds(place.bounds, { padding: [20, 20] });
    else map.current?.setView([place.lat, place.lon], place.zoom);
  }, [place]);

  return (
    <div className="map-frame">
      <div ref={container} className="map-canvas" />
      <p className="map-caption" aria-live="polite">
        {caption}
      </p>
      <div className="map-zoom">
        <button type="button" aria-label="Przybliż" onClick={() => map.current?.zoomIn()}>
          +
        </button>
        <button type="button" aria-label="Oddal" onClick={() => map.current?.zoomOut()}>
          −
        </button>
      </div>
    </div>
  );
}
