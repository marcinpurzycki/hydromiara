import { useState } from "react";
import type { Crop, CropHistory } from "../api/types";
import { HistoryForm } from "../components/HistoryForm";
import { lowerPl } from "../lib/format";
import { emptyDraft, givenCount, historyOfDraft, type HistoryDraft } from "../lib/history";

type Answer = "same" | "changed" | "unknown";

interface Props {
  cropName: string;
  years: number[];
  crops: Crop[];
  finished: boolean;
  /** Sends the answer; null withdraws an earlier one. */
  onAnswer: (history: CropHistory | null) => void;
  onFormOpen: (open: boolean) => void;
}

const LABELS: Record<Answer, string> = {
  same: "Tak, co roku",
  changed: "Nie, uprawy się zmieniały",
  unknown: "Nie wiem",
};

/** Optional question asked while the analysis runs; the analysis never waits for it. */
export function HistoryQuestion({ cropName, years, crops, finished, onAnswer, onFormOpen }: Props) {
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [draft, setDraft] = useState<HistoryDraft>(() => emptyDraft(years.length));
  const name = lowerPl(cropName);

  const showForm = (open: boolean) => {
    setFormOpen(open);
    onFormOpen(open);
  };

  const pick = (value: Answer) => {
    setAnswer(value);
    if (value === "same") onAnswer({ same_every_year: true });
    if (value === "unknown") onAnswer(null);
    if (value === "changed") showForm(true);
  };

  const reset = () => {
    setAnswer(null);
    onAnswer(null);
  };

  if (formOpen) {
    return (
      <section className="panel">
        <p className="eyebrow">Historia upraw · analiza biegnie dalej w tle</p>
        <h2>Co rosło tu w ostatnich {years.length} latach?</h2>
        <p className="hint">
          Wybierz uprawę dla lat, które pamiętasz — wcześniejsze lata uzupełnimy tą samą uprawą, możesz je
          poprawić. Lata puste liczymy „jak obecnie”.
        </p>
        <HistoryForm years={years} draft={draft} crops={crops} currentCropName={cropName} onChange={setDraft} />
        <div className="button-row history-actions">
          <button
            type="button"
            className="button button-primary"
            onClick={() => {
              onAnswer(givenCount(draft) > 0 ? historyOfDraft(years, draft) : null);
              showForm(false);
            }}
          >
            Zapisz historię upraw
          </button>
          <button
            type="button"
            className="link-button"
            onClick={() => {
              showForm(false);
              reset();
            }}
          >
            Wróć do pytania
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <p className="eyebrow">Pytanie dodatkowe · możesz pominąć</p>
      <p className="question">Czy na tej działce co roku rosła ta sama uprawa ({name})?</p>
      {answer === null ? (
        <>
          <div className="answers">
            {(Object.keys(LABELS) as Answer[]).map((value) => (
              <button key={value} type="button" onClick={() => pick(value)}>
                {LABELS[value]}
              </button>
            ))}
          </div>
          <p className="hint">
            {finished
              ? "Odpowiedź trafi do raportu po jego otwarciu. Możesz też od razu przejść do raportu."
              : "Analiza biegnie dalej bez względu na odpowiedź. Raport pokaże się sam, nawet jeśli nie odpowiesz."}
          </p>
        </>
      ) : (
        <>
          <div className="answer-chosen">{LABELS[answer]}</div>
          <div className="answer-info">
            {answer === "same" && <b>Zapisaliśmy: {name} przez ostatnie lata</b>}
            {answer === "changed" && (
              <b>
                Historia upraw podana dla {givenCount(draft)} z {years.length} lat
              </b>
            )}
            {answer === "unknown" && <b>W porządku</b>}
            <span className="muted">
              {answer === "unknown"
                ? "Przyjmiemy, że rosła tu obecna uprawa. Historię możesz uzupełnić później z poziomu raportu."
                : "W raporcie pojawi się przebieg historyczny. Lata niepodane liczymy „jak obecnie”."}
            </span>
          </div>
          <div className="button-row">
            {answer === "changed" && (
              <button type="button" className="link-button" onClick={() => showForm(true)}>
                Popraw lata
              </button>
            )}
            <button type="button" className="link-button" onClick={reset}>
              Zmień odpowiedź
            </button>
          </div>
        </>
      )}
    </section>
  );
}
