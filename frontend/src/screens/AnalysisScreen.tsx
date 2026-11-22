import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import type { SourceId, SourceState } from "../api/types";
import { readAnalysisInfo, useCrops } from "../lib/catalog";
import { datePl } from "../lib/format";
import { defaultWindow } from "../lib/history";
import { HistoryQuestion } from "./HistoryQuestion";
import { useAnalysis } from "./useAnalysis";

const SOURCES: [SourceId, string, string][] = [
  ["weather", "Pogoda", "Deszcz i parowanie z 10 lat"],
  ["satellite", "Zdjęcia z satelity", "Jak wyglądają rośliny na działce"],
  ["soil", "Gleba", "Ile wody potrafi zatrzymać"],
  ["hydro", "Woda w okolicy", "Rowy, rzeki i stawy"],
  ["terrain", "Ukształtowanie terenu", "Spadki i zagłębienia"],
];

const STATE_LABELS: Record<SourceState, string> = {
  wait: "Czeka",
  run: "Sprawdzamy…",
  done: "Gotowe",
  missing: "Brak danych",
};

const OPEN_DELAY_MS = 450;

export function AnalysisScreen() {
  const reportId = useParams().reportId ?? "";
  const navigate = useNavigate();
  const { crops } = useCrops();
  const info = useMemo(() => readAnalysisInfo(reportId), [reportId]);
  const { status, failure, missingReport, sendHistory, openReport } = useAnalysis(reportId);
  const [formOpen, setFormOpen] = useState(false);
  const opening = useRef(false);

  const done = status?.state === "done";
  const states = new Map(status?.sources.map((source) => [source.id, source]));
  const closed = SOURCES.filter(([id]) => ["done", "missing"].includes(states.get(id)?.state ?? "wait")).length;
  const missing = SOURCES.filter(([id]) => states.get(id)?.state === "missing");
  const writing = status?.state === "running" && closed === SOURCES.length;

  const open = async () => {
    if (opening.current) return;
    opening.current = true;
    navigate(await openReport(), { replace: true });
  };

  // The Report opens by itself unless the user is in the middle of the history form.
  useEffect(() => {
    if (!done || formOpen) return;
    const timer = setTimeout(() => void open(), OPEN_DELAY_MS);
    return () => clearTimeout(timer);
  }, [done, formOpen]);

  if (failure) {
    return (
      <div className="screen screen-text">
        <h1>{missingReport ? "Nie ma takiej analizy" : "Analiza się nie powiodła"}</h1>
        <div role="alert" className="notice notice-warning">
          <b>{failure}</b>
          <span>Raport nie powstał. Możesz uruchomić analizę jeszcze raz.</span>
        </div>
        <Link
          to="/"
          state={info && { prefill: { parcelId: info.parcelId, cropId: info.cropId, analysisDate: info.analysisDate } }}
          className="button button-primary button-large"
        >
          Wróć i spróbuj ponownie
        </Link>
      </div>
    );
  }

  const showQuestion = info !== null && info.cropId !== "bare_field";

  return (
    <div className="screen screen-narrow">
      <div>
        <h1 className="wrap-anywhere">{info ? `Sprawdzamy działkę ${info.parcelId}` : "Sprawdzamy działkę"}</h1>
        {info && (
          <p className="lead">
            {info.cropName}
            {info.region ? ` · ${info.region}` : ""} · Data analizy: {datePl(info.analysisDate)}
          </p>
        )}
      </div>

      <div className="card progress-card">
        <div className="progress-head">
          <strong aria-live="polite">
            Gotowe {closed} z {SOURCES.length}
          </strong>
          <span className="hint">
            {writing ? "Przygotowujemy raport…" : "zwykle trwa to do pół minuty"}
          </span>
        </div>
        <div className="progress-bar">
          <div style={{ width: `${(closed / SOURCES.length) * 100}%` }} />
        </div>
        {done && formOpen && (
          <div role="status" className="ready-row">
            <div>
              <b>Raport jest gotowy</b>
              <span className="muted">
                Możesz spokojnie dokończyć historię upraw albo przejść od razu do raportu.
              </span>
            </div>
            <button type="button" className="button button-primary" onClick={() => void open()}>
              Pomiń i zobacz raport
            </button>
          </div>
        )}
      </div>

      {missing.length > 0 && (
        <div role="status" className="notice notice-warning">
          <b>{missing.length === 1 ? "Jedno ze źródeł nie dało danych" : "Część źródeł nie dała danych"}</b>
          {missing.map(([id, name]) => (
            <span key={id}>
              {name}: {states.get(id)?.note ?? "brak danych"}
            </span>
          ))}
          <span>Raport powstanie z pozostałych danych, a pewność oceny może być niższa.</span>
        </div>
      )}

      <div className={showQuestion ? "analysis-grid" : "analysis-grid analysis-grid-single"}>
        <section className="card sources-card">
          <h2 className="eyebrow">Co sprawdzamy</h2>
          <ul className="sources">
            {SOURCES.map(([id, name, description]) => {
              const source = states.get(id);
              const state = source?.state ?? "wait";
              return (
                <li key={id} className={`source source-${state}`}>
                  <span className="source-dot">{state === "missing" ? "!" : ""}</span>
                  <div className="source-text">
                    <div className="source-name">{name}</div>
                    <div className="hint">{state === "done" && source?.note ? source.note : description}</div>
                  </div>
                  <span className="source-state">{STATE_LABELS[state]}</span>
                </li>
              );
            })}
          </ul>
        </section>
        {showQuestion && info && (
          <HistoryQuestion
            cropName={info.cropName}
            years={defaultWindow(info.analysisDate)}
            crops={crops}
            finished={done}
            onAnswer={sendHistory}
            onFormOpen={setFormOpen}
          />
        )}
      </div>
    </div>
  );
}
