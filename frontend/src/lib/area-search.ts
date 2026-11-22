// Administrative units by their TERYT identifier, read straight from the public
// ULDK service of GUGiK. Like the address search, it only moves the map.
import type { Place } from "./geocoder";

const SERVICE = "https://uldk.gugik.gov.pl/";

export interface AreaRequest {
  request: "GetRegionById" | "GetCommuneById" | "GetCountyById" | "GetVoivodeshipById";
  id: string;
  /** Attributes asked for; the extent is always the last one. */
  result: string;
  label: (names: string[]) => string;
  zoom: number;
}

/** What to ask for a text that is a TERYT identifier of a unit; null for any other text. */
export function areaRequest(text: string): AreaRequest | null {
  const query = text.trim().replace(/\.$/, "");
  if (/^\d{6}_\d\.\d{4}$/.test(query)) {
    return {
      request: "GetRegionById",
      id: query,
      result: "region,commune,geom_extent",
      label: ([region, commune]) => `obręb ${region}, gmina ${commune}`,
      zoom: 14,
    };
  }
  // A commune: 040704_2, the same written as seven digits, or six digits without the kind.
  const commune = /^(\d{6})_?(\d)?$/.exec(query);
  if (commune) {
    return {
      request: "GetCommuneById",
      id: commune[2] ? `${commune[1]}_${commune[2]}` : commune[1],
      result: "commune,county,geom_extent",
      label: ([name, county]) => `gmina ${name}, ${county}`,
      zoom: 12,
    };
  }
  if (/^\d{4}$/.test(query)) {
    return { request: "GetCountyById", id: query, result: "county,geom_extent", label: ([name]) => name, zoom: 10 };
  }
  if (/^\d{2}$/.test(query)) {
    return {
      request: "GetVoivodeshipById",
      id: query,
      result: "voivodeship,geom_extent",
      label: ([name]) => `województwo ${name}`,
      zoom: 8,
    };
  }
  return null;
}

/**
 * Reads an answer of the service: the first line is the status (0 = found),
 * the second holds the attributes separated by "|", the extent last, as
 * "west,south,east,north" in degrees.
 */
export function placeFromAnswer(answer: string, asked: AreaRequest): Place | null {
  const [status, line] = answer.trim().split(/\r?\n/);
  if (status?.trim() !== "0" || !line) return null;
  const fields = line.split("|");
  const extent = (fields.pop() ?? "").split(",").map(Number);
  if (extent.length !== 4 || extent.some((value) => !Number.isFinite(value))) return null;
  const [west, south, east, north] = extent;
  return {
    label: asked.label(fields),
    lat: (south + north) / 2,
    lon: (west + east) / 2,
    zoom: asked.zoom,
    bounds: [
      [south, west],
      [north, east],
    ],
  };
}

export async function findArea(asked: AreaRequest, signal?: AbortSignal): Promise<Place | null> {
  const params = new URLSearchParams({ request: asked.request, id: asked.id, result: asked.result, srid: "4326" });
  const response = await fetch(`${SERVICE}?${params}`, { signal });
  if (!response.ok) throw new Error("area service unavailable");
  return placeFromAnswer(await response.text(), asked);
}
