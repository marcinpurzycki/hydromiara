import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { ApiError, api, errorMessage, sleep } from "../api/client";
import type { Example } from "../api/types";
import { CropPicker } from "../components/CropPicker";
import { DateField } from "../components/DateField";
import { ExamplesMenu } from "../components/ExamplesMenu";
import { ParcelMap } from "../components/ParcelMap";
import { SystemInfo } from "../components/SystemInfo";
import { storeAnalysisInfo, useCrops } from "../lib/catalog";
import { todayIso } from "../lib/format";
import { parcelLabel } from "../lib/parcel-search";
import { ParcelChoice, ParcelMissing } from "./ParcelViews";
import { useParcelPicker } from "./useParcelPicker";

export interface StartPrefill {
  parcelId: string;
  cropId: string;
  analysisDate: string;
}

const START_TRIES = 6;
const CAPACITY_WAIT_S = 10;
// A refusal for too many requests is waited out only within the minute limit.
const RATE_WAIT_MAX_S = 60;

export function StartScreen() {
  const navigate = useNavigate();
  const prefill = (useLocation().state as { prefill?: StartPrefill } | null)?.prefill;
  const { crops, failed: cropsFailed } = useCrops();
  const picker = useParcelPicker(prefill?.parcelId ?? "");
  const [cropId, setCropId] = useState<string | null>(prefill?.cropId ?? null);
  const [date, setDate] = useState(prefill?.analysisDate ?? todayIso());
  const [cropError, setCropError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const { load } = picker;
  useEffect(() => {
    if (prefill) void load(prefill.parcelId);
  }, [prefill, load]);

  const useExample = (example: Example) => {
    setCropId(example.crop_id);
    setDate(example.analysis_date);
    setCropError(null);
    void load(example.parcel_id);
  };

  /**
   * The service runs a few analyses at a time and limits starts per address;
   * a refusal for lack of room or a short refusal for too many starts is retried.
   */
  const startAnalysis = async (parcelId: string, crop: string) => {
    for (let attempt = 1; ; attempt++) {
      try {
        return await api.startAnalysis(parcelId, crop, date);
      } catch (failure) {
        const code = failure instanceof ApiError ? failure.code : "";
        const waitS = failure instanceof ApiError ? failure.retryAfterS : null;
        const busy = code === "analysis_capacity_reached";
        const limited = code === "rate_limited" && waitS !== null && waitS <= RATE_WAIT_MAX_S;
        if ((!busy && !limited) || attempt >= START_TRIES) throw failure;
        setNotice(
          busy
            ? "Serwer liczy teraz inne analizy. Czekamy na wolne miejsce, to potrwa chwilę…"
            : `Z tego adresu uruchomiono przed chwilą kilka analiz. Zaczniemy za ${waitS} s…`,
        );
        await sleep((waitS ?? CAPACITY_WAIT_S) * 1000);
        setNotice(null);
      }
    }
  };

  const submit = async () => {
    setNotice(null);
    const crop = crops.find((item) => item.id === cropId);
    if (!crop) {
      setCropError("Zaznacz, co rośnie na działce, albo wyszukaj uprawę.");
      return;
    }
    setStarting(true);
    try {
      const parcel = picker.parcel ?? (await picker.search());
      if (!parcel) return;
      const started = await startAnalysis(parcel.parcel_id, crop.id);
      storeAnalysisInfo(started.report_id, {
        parcelId: parcel.parcel_id,
        region: parcel.region,
        cropId: crop.id,
        cropName: crop.name,
        analysisDate: date,
      });
      navigate(`/analiza/${started.report_id}`);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "unknown_crop") setCropError(failure.message);
      else setNotice(errorMessage(failure));
    } finally {
      setStarting(false);
    }
  };

  if (picker.view.kind === "choice") {
    return (
      <ParcelChoice
        query={picker.text}
        matches={picker.view.matches}
        onChoose={picker.choose}
        onBack={picker.backToForm}
      />
    );
  }
  if (picker.view.kind === "missing") return <ParcelMissing query={picker.text} onBack={picker.backToForm} />;

  return (
    <div className="screen screen-wide">
      <div className="heading-row">
        <div>
          <h1>Wybierz działkę i uprawę</h1>
          <p className="lead">W dwie minuty sprawdzisz, ile wody ma Twoje pole.</p>
        </div>
        <SystemInfo />
      </div>
      <div className="start-grid">
        <section className="card start-form">
          <form
            className="field"
            onSubmit={(event) => {
              event.preventDefault();
              void picker.search();
            }}
          >
            <label className="field-label" htmlFor="parcel">
              Wpisz adres lub działkę albo wybierz na mapie
            </label>
            <div className="search-row">
              <input
                id="parcel"
                type="text"
                autoComplete="off"
                maxLength={120}
                placeholder="Adres, numer działki z obrębem, identyfikator lub TERYT"
                value={picker.text}
                onChange={(event) => picker.setText(event.target.value)}
              />
              <button type="submit" className="button button-large button-soft" disabled={picker.searching}>
                {picker.searching ? "Szukamy…" : "Szukaj"}
              </button>
            </div>
            {picker.places.length > 0 && (
              <ul className="place-list">
                {picker.places.map((place) => (
                  <li key={`${place.lat},${place.lon}`}>
                    <button type="button" onClick={() => picker.goToPlace(place, picker.places)}>
                      {place.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {picker.hint && (
              <p className="hint" role="status">
                {picker.hint}
              </p>
            )}
            {picker.error && <p className="field-error">{picker.error}</p>}
          </form>

          {cropsFailed && <p className="field-error">Nie udało się pobrać listy upraw. Odśwież stronę.</p>}
          <CropPicker
            crops={crops}
            cropId={cropId}
            error={cropError}
            onChange={(id) => {
              setCropId(id);
              setCropError(null);
            }}
          />
          <DateField value={date} onChange={setDate} />

          {notice && (
            <p className="notice notice-warning" role="status">
              {notice}
            </p>
          )}
          <div className="start-actions">
            <button
              type="button"
              className="button button-primary button-huge"
              disabled={starting}
              onClick={() => void submit()}
            >
              {starting ? "Uruchamiamy analizę…" : "Zbadaj nawodnienie pola"}
            </button>
            <ExamplesMenu crops={crops} onPick={useExample} />
          </div>
        </section>

        <section className="start-map">
          <p className="chosen-parcel">
            Wybrana działka:{" "}
            {picker.parcel ? <span>{parcelLabel(picker.parcel)}</span> : <i>wybierz na mapie</i>}
          </p>
          <ParcelMap
            geometry={picker.parcel?.geometry ?? null}
            place={picker.place}
            caption={picker.caption}
            onPick={picker.pickOnMap}
          />
        </section>
      </div>
    </div>
  );
}
