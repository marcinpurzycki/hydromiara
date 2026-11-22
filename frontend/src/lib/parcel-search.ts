// What the text typed into the parcel field leads to.
import { ApiError, api } from "../api/client";
import type { ParcelMatch } from "../api/types";
import { areaRequest, findArea } from "./area-search";
import { findPlaces, looksLikeParcelId, type Place } from "./geocoder";

export type SearchOutcome =
  | { kind: "parcel"; parcel: ParcelMatch }
  | { kind: "choice"; matches: ParcelMatch[] }
  | { kind: "places"; places: Place[] }
  /** The text named a parcel and the register has none like it. */
  | { kind: "none" }
  /** The text is neither a parcel nor a place the map can be moved to. */
  | { kind: "unknown" };

/** The search does not return the outline, so it is fetched for the chosen parcel. */
export async function withGeometry(match: ParcelMatch): Promise<ParcelMatch> {
  return match.geometry ? match : api.parcel(match.parcel_id);
}

/** Parcels of the register, or null when the text does not have the form of a parcel. */
async function parcelMatches(text: string): Promise<ParcelMatch[] | null> {
  try {
    return await api.searchParcels(text);
  } catch (error) {
    if (error instanceof ApiError && error.code === "invalid_parcel_query") return null;
    throw error;
  }
}

/**
 * TERYT identifier of a precinct, commune, county or voivodeship → the map shows that unit;
 * parcel identifier or number with precinct → parcels of the register;
 * anything else (or no parcel found) → address search. Places only move the map.
 */
export async function resolveQuery(text: string): Promise<SearchOutcome> {
  const query = text.trim();
  const area = areaRequest(query);
  if (area) {
    const place = await findArea(area).catch(() => null);
    return place ? { kind: "places", places: [place] } : { kind: "unknown" };
  }
  const matches = await parcelMatches(query);
  if (matches?.length === 1) return { kind: "parcel", parcel: await withGeometry(matches[0]) };
  if (matches && matches.length > 1) return { kind: "choice", matches };
  if (looksLikeParcelId(query)) return { kind: "none" };
  const places = await findPlaces(query).catch(() => []);
  if (places.length > 0) return { kind: "places", places };
  return matches ? { kind: "none" } : { kind: "unknown" };
}

export const parcelLabel = (parcel: ParcelMatch) =>
  parcel.region ? `${parcel.parcel_id} · ${parcel.region}` : parcel.parcel_id;
