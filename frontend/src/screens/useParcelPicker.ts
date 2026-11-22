// State of the parcel choice on the Start screen: text search, map clicks, list of matches.
import { useCallback, useRef, useState } from "react";
import { api, errorMessage } from "../api/client";
import type { ParcelMatch } from "../api/types";
import type { Place } from "../lib/geocoder";
import { resolveQuery, withGeometry } from "../lib/parcel-search";

export type PickerView = { kind: "form" } | { kind: "choice"; matches: ParcelMatch[] } | { kind: "missing" };

const CAPTION_START = "Kliknij na mapie, aby wskazać działkę";
const CAPTION_PLACE = "Kliknij swoją działkę na mapie";
const LOCATION_ZOOM = 17;
const LOCATION_TIMEOUT_MS = 15_000;
const NOT_FOUND =
  "Nie znaleźliśmy takiego miejsca. Wpisz adres (np. Płońsk, Warszawska 5), numer działki z nazwą obrębu, " +
  "identyfikator działki albo numer TERYT obrębu lub gminy.";

export function useParcelPicker(initialText: string) {
  const [text, setTextValue] = useState(initialText);
  const [parcel, setParcel] = useState<ParcelMatch | null>(null);
  const [view, setView] = useState<PickerView>({ kind: "form" });
  const [places, setPlaces] = useState<Place[]>([]);
  const [place, setPlace] = useState<Place | null>(null);
  const [caption, setCaption] = useState(CAPTION_START);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [searching, setSearching] = useState(false);
  const clicks = useRef(0);

  const select = useCallback((chosen: ParcelMatch) => {
    setParcel(chosen);
    setTextValue(chosen.parcel_id);
    setPlaces([]);
    setError(null);
    setHint(null);
    setView({ kind: "form" });
    setCaption(`Wybrano działkę ${chosen.number}${chosen.region ? `, ${chosen.region}` : ""}`);
  }, []);

  const setText = (value: string) => {
    setTextValue(value);
    setError(null);
    setHint(null);
    setPlaces([]);
    if (parcel && value.trim() !== parcel.parcel_id) setParcel(null);
  };

  /** Moves the map; the other places found stay listed until one is chosen or a parcel is picked. */
  const goToPlace = (target: Place, others: Place[] = []) => {
    setPlace({ ...target });
    setPlaces(others);
    setCaption(CAPTION_PLACE);
    setHint(`Pokazujemy na mapie: ${target.label}. Teraz kliknij swoją działkę.`);
  };

  /** Moves the map to where the device is; the parcel is still picked by a click. */
  const locate = () => {
    if (!("geolocation" in navigator)) {
      setError("Ta przeglądarka nie podaje lokalizacji. Wpisz adres albo wskaż działkę na mapie.");
      return;
    }
    setLocating(true);
    setError(null);
    setHint(null);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocating(false);
        const { latitude: lat, longitude: lon } = coords;
        // The same rectangle of Poland the API accepts for a click on the map.
        if (lat > 49 && lat < 54.9 && lon > 14 && lon < 24.2) {
          goToPlace({ label: "Twoja lokalizacja", lat, lon, zoom: LOCATION_ZOOM });
        } else {
          setError("Twoja lokalizacja jest poza Polską. Wpisz adres albo wskaż działkę na mapie.");
        }
      },
      (failure) => {
        setLocating(false);
        setError(
          failure.code === failure.PERMISSION_DENIED
            ? "Przeglądarka nie udostępniła lokalizacji. Zezwól na nią dla tej strony albo wpisz adres."
            : "Nie udało się ustalić lokalizacji. Spróbuj ponownie albo wpisz adres.",
        );
      },
      { enableHighAccuracy: true, timeout: LOCATION_TIMEOUT_MS, maximumAge: 60_000 },
    );
  };

  /** A click picks the parcel under it; a newer click overrides an answer still on its way. */
  const pickOnMap = async (lat: number, lon: number) => {
    const turn = ++clicks.current;
    setCaption("Szukamy działki w tym miejscu…");
    try {
      const found = await api.parcelAt(lon, lat);
      if (turn !== clicks.current) return;
      if (found) select(found);
      else setCaption("W tym miejscu nie ma działki w ewidencji. Kliknij w inne miejsce.");
    } catch (failure) {
      if (turn === clicks.current) setCaption(errorMessage(failure));
    }
  };

  /** Runs the text search; resolves to the parcel when the text names exactly one. */
  const search = async (): Promise<ParcelMatch | null> => {
    if (!text.trim()) {
      setError("Wpisz adres, numer działki z nazwą obrębu albo identyfikator działki.");
      return null;
    }
    setSearching(true);
    setError(null);
    setHint(null);
    try {
      const outcome = await resolveQuery(text);
      if (outcome.kind === "parcel") {
        select(outcome.parcel);
        return outcome.parcel;
      }
      if (outcome.kind === "choice") setView({ kind: "choice", matches: outcome.matches });
      else if (outcome.kind === "none") setView({ kind: "missing" });
      else if (outcome.kind === "unknown") setError(NOT_FOUND);
      else goToPlace(outcome.places[0], outcome.places.length > 1 ? outcome.places : []);
      return null;
    } catch (failure) {
      setError(errorMessage(failure));
      return null;
    } finally {
      setSearching(false);
    }
  };

  const choose = async (match: ParcelMatch) => {
    try {
      select(await withGeometry(match));
    } catch (failure) {
      setView({ kind: "form" });
      setError(errorMessage(failure));
    }
  };

  /** Fills the field with a known identifier and outlines the parcel. */
  const load = useCallback(
    async (parcelId: string) => {
      setTextValue(parcelId);
      try {
        select(await api.parcel(parcelId));
      } catch {
        // The outline is a convenience here; the search runs again on submit.
      }
    },
    [select],
  );

  return {
    text, parcel, view, places, place, caption, error, hint, searching, locating, locate,
    setText, setError, pickOnMap, search, choose, load, goToPlace,
    backToForm: () => setView({ kind: "form" }),
  };
}
