// What the text typed into the parcel field leads to.
import { ApiError, api } from "../api/client";
import type { ParcelMatch } from "../api/types";
import { findPlaces, looksLikeParcelId, type Place } from "./geocoder";

export type SearchOutcome =
  | { kind: "parcel"; parcel: ParcelMatch }
  | { kind: "choice"; matches: ParcelMatch[] }
  | { kind: "places"; places: Place[] }
  | { kind: "none" };

/** The search does not return the outline, so it is fetched for the chosen parcel. */
export async function withGeometry(match: ParcelMatch): Promise<ParcelMatch> {
  return match.geometry ? match : api.parcel(match.parcel_id);
}

async function parcelMatches(text: string): Promise<ParcelMatch[]> {
  try {
    return await api.searchParcels(text);
  } catch (error) {
    // Not a parcel identifier nor a number with a precinct: maybe an address.
    if (error instanceof ApiError && error.code === "invalid_parcel_query") return [];
    throw error;
  }
}

/**
 * Parcel identifier or number with precinct → parcels of the register;
 * anything else (or no parcel found) → address search that only moves the map.
 */
export async function resolveQuery(text: string): Promise<SearchOutcome> {
  const query = text.trim();
  const matches = await parcelMatches(query);
  if (matches.length === 1) return { kind: "parcel", parcel: await withGeometry(matches[0]) };
  if (matches.length > 1) return { kind: "choice", matches };
  if (looksLikeParcelId(query)) return { kind: "none" };
  try {
    const places = await findPlaces(query);
    return places.length > 0 ? { kind: "places", places } : { kind: "none" };
  } catch {
    return { kind: "none" };
  }
}

export const parcelLabel = (parcel: ParcelMatch) =>
  parcel.region ? `${parcel.parcel_id} · ${parcel.region}` : parcel.parcel_id;
