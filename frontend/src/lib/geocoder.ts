// Address search with the public geocoding service of GUGiK (Usługa Uniwersalnego
// Geokodowania). It only moves the map; the parcel is always taken from our API.
// The service expects "locality, street number" (its own example: "Marki, Andersa 1"),
// so a text typed in another order is also asked in that order.

const SERVICE = "https://services.gugik.gov.pl/uug/";

export interface Place {
  label: string;
  lat: number;
  lon: number;
  zoom: number;
  /** Extent to show instead of a point: [[south, west], [north, east]]. */
  bounds?: [[number, number], [number, number]];
}

// Map zoom by what the service says it found.
const ZOOM_BY_TYPE: Record<string, number> = { address: 18, street: 16, city: 13 };
const DEFAULT_ZOOM = 15;
const MAX_VARIANTS = 4;

interface RawResult {
  city?: string | null;
  street?: string | null;
  number?: string | null;
  commune?: string | null;
  county?: string | null;
  x?: string | number | null;
  y?: string | number | null;
}

function label(result: RawResult): string {
  const street = [result.street, result.number].filter(Boolean).join(" ");
  const first = [result.city, street].filter(Boolean).join(", ");
  const area = result.commune && result.commune !== result.city ? `gmina ${result.commune}` : "";
  return [first, area, result.county ? `powiat ${result.county}` : ""].filter(Boolean).join(", ");
}

/**
 * The typed address in the orders worth asking, the typed one first:
 * "street number, locality" and "street number locality" are turned into
 * "locality, street number"; "locality street number" gets its comma.
 */
export function addressVariants(text: string): string[] {
  const clean = text
    .replace(/\b\d{2}-\d{3}\b/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s*,\s*/g, ", ")
    .replace(/^[, ]+|[, ]+$/g, "");
  const variants = [clean];
  if (clean.includes(",")) {
    const parts = clean.split(", ").filter(Boolean);
    if (parts.length === 2) variants.push(`${parts[1]}, ${parts[0]}`);
  } else {
    const words = clean.split(" ");
    const number = words.findIndex((word) => /\d/.test(word));
    const join = (from: number, to?: number) => words.slice(from, to).join(" ");
    if (number > 0 && number < words.length - 1) variants.push(`${join(number + 1)}, ${join(0, number + 1)}`);
    if (number > 1) variants.push(`${words[0]}, ${join(1)}`);
    if (number > 2) variants.push(`${join(0, 2)}, ${join(2)}`);
  }
  return [...new Set(variants.filter(Boolean))].slice(0, MAX_VARIANTS);
}

/** Places matching an address or a locality name; empty when nothing was found. */
export async function findPlaces(text: string, signal?: AbortSignal): Promise<Place[]> {
  for (const variant of addressVariants(text)) {
    const places = await askService(variant, signal);
    if (places.length > 0) return places;
  }
  return [];
}

async function askService(text: string, signal?: AbortSignal): Promise<Place[]> {
  const params = new URLSearchParams({ request: "GetAddress", address: text, srid: "4326" });
  const response = await fetch(`${SERVICE}?${params}`, { signal });
  if (!response.ok) throw new Error("geocoder unavailable");
  const body = (await response.json()) as { type?: string; results?: Record<string, RawResult> | null };
  const zoom = ZOOM_BY_TYPE[body.type ?? ""] ?? DEFAULT_ZOOM;
  const places: Place[] = [];
  for (const result of Object.values(body.results ?? {})) {
    const lon = Number(result.x);
    const lat = Number(result.y);
    // With srid=4326 the service answers x = longitude, y = latitude.
    if (Number.isFinite(lon) && Number.isFinite(lat) && lat > 48 && lat < 56 && lon > 13 && lon < 25) {
      places.push({ label: label(result) || text, lat, lon, zoom });
    }
  }
  return places.slice(0, 5);
}

export const looksLikeParcelId = (text: string) => /^\d{6}_\d\.\d{4}\./.test(text.trim());
