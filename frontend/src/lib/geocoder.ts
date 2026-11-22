// Address search with the public geocoding service of GUGiK (Usługa Uniwersalnego
// Geokodowania). It only moves the map; the parcel is always taken from our API.

const SERVICE = "https://services.gugik.gov.pl/uug/";

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

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

/** Places matching an address or a locality name; empty when nothing was found. */
export async function findPlaces(text: string, signal?: AbortSignal): Promise<Place[]> {
  const params = new URLSearchParams({ request: "GetAddress", address: text, srid: "4326" });
  const response = await fetch(`${SERVICE}?${params}`, { signal });
  if (!response.ok) throw new Error("geocoder unavailable");
  const body = (await response.json()) as { results?: Record<string, RawResult> | null };
  const places: Place[] = [];
  for (const result of Object.values(body.results ?? {})) {
    const lon = Number(result.x);
    const lat = Number(result.y);
    // With srid=4326 the service answers x = longitude, y = latitude.
    if (Number.isFinite(lon) && Number.isFinite(lat) && lat > 48 && lat < 56 && lon > 13 && lon < 25) {
      places.push({ label: label(result) || text, lat, lon });
    }
  }
  return places.slice(0, 5);
}

export const looksLikeParcelId = (text: string) => /^\d{6}_\d\.\d{4}\./.test(text.trim());
