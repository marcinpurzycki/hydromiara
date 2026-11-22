import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError, api, errorMessage } from "../api/client";
import type { CompareResponse, CropSusceptibility, RankingResponse } from "../api/types";
import { Chevron } from "../components/Icon";
import { YearLegend, YearStrip, type StripYear } from "../components/YearStrip";
import { useCrops } from "../lib/catalog";
import { lowerPl, twoDigitYear } from "../lib/format";
import { byDeficitShare } from "../lib/report-view";
import { useReport } from "../lib/use-report";
import { ReportGate, ReportHeading, prefillOf } from "./ReportScreen";

type Mode = "ranking" | "compare";
const MODES: [Mode, string][] = [
  ["ranking", "Uprawy najmniej narażone"],
  ["compare", "Sprawdź inną uprawę"],
];

const strip = (compare: CompareResponse | undefined, side: "current_deficit" | "other_deficit"): StripYear[] =>
  (compare?.years ?? []).map((year) => ({
    key: year.year,
    label: twoDigitYear(year.year),
    state: year[side] ? "deficit" : "ok",
    partial: year.partial,
    description: String(year.year),
  }));

function Row({ crop, years, current }: { crop: CropSusceptibility; years: StripYear[]; current: boolean }) {
  return (
    <li className={current ? "sim-row sim-row-current" : "sim-row"}>
      <span className="sim-name">
        {crop.name}
        {current && <small>obecna uprawa</small>}
      </span>
      <YearStrip years={years} small />
      <span className="sim-count">
        {crop.deficit_years} z {crop.total_years} lat
      </span>
    </li>
  );
}

function sentence(compare: CompareResponse): string {
  const { current, other } = compare;
  const difference = current.deficit_years - other.deficit_years;
  const outcome =
    difference > 0 ? `rzadziej (o ${difference})` : difference < 0 ? `częściej (o ${-difference})` : "tak samo często";
  return (
    `${current.name}: wody brakowało w ${current.deficit_years} z ${current.total_years} lat. ` +
    `${other.name}: w ${other.deficit_years} z ${other.total_years} lat. ` +
    `Uprawie „${lowerPl(other.name)}” wody brakowałoby ${outcome}.`
  );
}

export function SimulationScreen() {
  const reportId = useParams().reportId ?? "";
  const load = useReport(reportId);
  const { crops } = useCrops();
  const [mode, setMode] = useState<Mode>("ranking");
  const [ranking, setRanking] = useState<RankingResponse | null>(null);
  const [compared, setCompared] = useState<Record<string, CompareResponse>>({});
  const [otherId, setOtherId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [outdated, setOutdated] = useState(false);
  const fail = (failure: unknown) => {
    setError(errorMessage(failure));
    setOutdated(failure instanceof ApiError && failure.code === "report_outdated");
  };
  const ready = load.state === "ready";

  // The ranking carries only counts; the years of each row come from the comparison.
  useEffect(() => {
    if (!ready) return;
    let active = true;
    api.ranking(reportId).then(
      (result) => {
        if (!active) return;
        setRanking(result);
        setOtherId((chosen) => chosen || result.top[0]?.crop_id || "");
        for (const crop of result.top) {
          api.compare(reportId, crop.crop_id).then(
            (compare) => active && setCompared((all) => ({ ...all, [crop.crop_id]: compare })),
            () => undefined,
          );
        }
      },
      (failure) => active && fail(failure),
    );
    return () => {
      active = false;
    };
  }, [ready, reportId]);

  useEffect(() => {
    if (!ready || !otherId || compared[otherId]) return;
    let active = true;
    api.compare(reportId, otherId).then(
      (compare) => active && setCompared((all) => ({ ...all, [otherId]: compare })),
      (failure) => active && fail(failure),
    );
    return () => {
      active = false;
    };
  }, [ready, reportId, otherId, compared]);

  if (load.state !== "ready") return <ReportGate load={load} reportId={reportId} />;
  const report = load.report;
  const back = `/raport/${reportId}`;
  const others = crops.filter((crop) => crop.id !== report.meta.crop.id && crop.id !== "bare_field");
  const anyCompare = Object.values(compared)[0];
  const chosen = compared[otherId];

  return (
    <div className="screen screen-narrow">
      <div className="heading-row">
        <ReportHeading report={report} title="Symulacja: inne uprawy na działce" />
        <Link to={back} className="button button-soft no-print">
          Wróć do raportu
        </Link>
      </div>
      <p className="text-column">
        Sprawdzamy, jak często innym uprawom brakowałoby wody na tej samej działce w tych samych latach. Miara jest
        ta sama co w raporcie: liczba lat z niedoborem wody.
      </p>
      {error && (
        <div role="alert" className="notice notice-warning">
          <b>{error}</b>
          {outdated && (
            <Link to="/" state={{ prefill: prefillOf(report) }} className="link-button no-print">
              Uruchom analizę jeszcze raz
            </Link>
          )}
        </div>
      )}
      {ranking && (
        <>
          <div className="tabs no-print" role="tablist">
            {MODES.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={mode === id}
                className={mode === id ? "tab tab-on" : "tab"}
                onClick={() => setMode(id)}
              >
                {label}
              </button>
            ))}
          </div>
          {mode === "ranking" ? (
            <section className="sim-section">
              <h2>Uprawy najmniej narażone na niedobór wody na tej działce</h2>
              {ranking.top.length === 0 && <p>Na liście nie ma teraz innej uprawy do porównania.</p>}
              <ol className="sim-list">
                {[...ranking.top, ranking.current]
                  .sort(byDeficitShare)
                  .map((crop) => {
                    const current = crop.crop_id === ranking.current.crop_id;
                    const years = current
                      ? strip(anyCompare, "current_deficit")
                      : strip(compared[crop.crop_id], "other_deficit");
                    return <Row key={crop.crop_id} crop={crop} years={years} current={current} />;
                  })}
              </ol>
            </section>
          ) : (
            <section className="sim-section">
              <h2>Sprawdź inną uprawę</h2>
              <div className="field sim-select">
                <label className="field-label" htmlFor="other">
                  Uprawa do porównania z obecną
                </label>
                <div className="select-wrap">
                  <select id="other" value={otherId} onChange={(event) => setOtherId(event.target.value)}>
                    {others.map((crop) => (
                      <option key={crop.id} value={crop.id}>
                        {crop.name}
                      </option>
                    ))}
                  </select>
                  <Chevron open={false} />
                </div>
              </div>
              {chosen && (
                <>
                  <ol className="sim-list" aria-live="polite">
                    <Row crop={chosen.current} years={strip(chosen, "current_deficit")} current />
                    <Row crop={chosen.other} years={strip(chosen, "other_deficit")} current={false} />
                  </ol>
                  <p>{sentence(chosen)}</p>
                  {chosen.years.length < chosen.current.total_years && (
                    <p className="hint">Paski pokazują tylko lata, w których obie uprawy mają ocenę.</p>
                  )}
                </>
              )}
            </section>
          )}
          <YearLegend partial={(anyCompare?.years ?? []).some((year) => year.partial)} />
          <section className="notice notice-warning text-column">
            <b>Czego symulacja nie uwzględnia</b>
            {ranking.limitations.map((item) => (
              <span key={item.text}>{item.text}</span>
            ))}
            <span>To porównanie, a nie wskazanie, co siać. Zmianę uprawy omów z doradcą.</span>
          </section>
        </>
      )}
      <div className="no-print">
        <Link to={back} className="button button-primary">
          Wróć do raportu
        </Link>
      </div>
    </div>
  );
}
