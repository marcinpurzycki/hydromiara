// Flat drawing of a parcel with its surroundings, computed from GeoJSON (EPSG:4326).
import type { GeoJsonGeometry, ReportMap } from "../api/types";

export const SKETCH_SIZE = 400;
const MARGIN = 0.28;

type Position = [number, number];
type Line = Position[];

function isPosition(value: unknown): value is Position {
  return Array.isArray(value) && typeof value[0] === "number" && typeof value[1] === "number";
}

/** All lines of a geometry (rings of polygons included); points become one-point lines. */
export function linesOf(geometry: GeoJsonGeometry): Line[] {
  const lines: Line[] = [];
  const walk = (value: unknown) => {
    if (!Array.isArray(value) || value.length === 0) return;
    if (isPosition(value)) lines.push([value]);
    else if (isPosition(value[0])) lines.push(value.filter(isPosition));
    else value.forEach(walk);
  };
  walk(geometry.coordinates);
  return lines;
}

export interface Sketch {
  parcel: string[];
  water: { path: string; closed: boolean; name: string | null }[];
  sites: { path: string; closed: boolean; label: string }[];
  arrow: { x1: number; y1: number; x2: number; y2: number } | null;
}

const isArea = (geometry: GeoJsonGeometry) => geometry.type === "Polygon" || geometry.type === "MultiPolygon";

/** Projects the Report map onto a square; north is up, distances keep their proportions. */
export function buildSketch(map: ReportMap): Sketch | null {
  const parcelLines = linesOf(map.parcel_geometry);
  const points = parcelLines.flat();
  if (points.length < 3) return null;
  const lons = points.map((point) => point[0]);
  const lats = points.map((point) => point[1]);
  const [west, east] = [Math.min(...lons), Math.max(...lons)];
  const [south, north] = [Math.min(...lats), Math.max(...lats)];
  // One degree of longitude is shorter than one of latitude by the cosine of the latitude.
  const shrink = Math.cos((((south + north) / 2) * Math.PI) / 180);
  const width = (east - west) * shrink;
  const height = north - south;
  const span = Math.max(width, height) * (1 + 2 * MARGIN) || 1;
  const scale = SKETCH_SIZE / span;
  const project = ([lon, lat]: Position): Position => [
    SKETCH_SIZE / 2 + ((lon - (west + east) / 2) * shrink) * scale,
    SKETCH_SIZE / 2 - (lat - (south + north) / 2) * scale,
  ];
  const path = (line: Line, closed: boolean) =>
    line.map((point, index) => `${index ? "L" : "M"}${project(point).map((n) => n.toFixed(1)).join(" ")}`).join("") +
    (closed ? "Z" : "");
  const paths = (geometry: GeoJsonGeometry) =>
    linesOf(geometry)
      .filter((line) => line.length > 1)
      .map((line) => ({ path: path(line, isArea(geometry)), closed: isArea(geometry) }));

  let arrow: Sketch["arrow"] = null;
  if (map.downhill_direction) {
    // Azimuth: 0° = north, clockwise; on the drawing north is up.
    const angle = (map.downhill_direction.azimuth_deg * Math.PI) / 180;
    const length = (Math.min(width, height) * scale) / 2.4 || SKETCH_SIZE / 6;
    const dx = Math.sin(angle) * length;
    const dy = -Math.cos(angle) * length;
    const centre = SKETCH_SIZE / 2;
    arrow = { x1: centre - dx, y1: centre - dy, x2: centre + dx, y2: centre + dy };
  }

  return {
    parcel: parcelLines.filter((line) => line.length > 2).map((line) => path(line, true)),
    water: map.water_objects.flatMap((object) => paths(object.geometry).map((p) => ({ ...p, name: object.name }))),
    sites: map.retention_sites.flatMap((site) => paths(site.geometry).map((p) => ({ ...p, label: site.label }))),
    arrow,
  };
}
