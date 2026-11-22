import { useState } from "react";
import { Link } from "react-router";
import type { Cause, Report } from "../api/types";
import { Arrow, Chevron, Icon } from "../components/Icon";
import { lowerPl } from "../lib/format";
import {
  CAUSE_ICONS,
  CAUSE_TITLES,
  foundCauses,
  indicatorText,
  noCausesSentence,
  unjudgedCauses,
} from "../lib/report-view";
import { ParcelSketch } from "./ParcelSketch";

/** Tiles of the causes found; a tile opens the path cause → advice → effect. */
export function Causes({ report, allOpen }: { report: Report; allOpen: boolean }) {
  const [chosen, setChosen] = useState<string | null>(null);
  const found = foundCauses(report);
  const unjudged = unjudgedCauses(report);

  if (report.causes.length === 0) {
    return (
      <div className="notice notice-plain">
        <b>{noCausesSentence(report)}</b>
      </div>
    );
  }

  const open = found.filter((cause) => allOpen || cause.id === chosen);
  return (
    <>
      {found.length === 0 && (
        <div className="notice notice-plain">
          <b>Nie stwierdzono żadnej z badanych przyczyn niedoboru wody.</b>
        </div>
      )}
      {found.length > 0 && (
        <section className={`cause-tiles cause-tiles-${found.length} print-section`}>
          {found.map((cause) => {
            const on = !allOpen && cause.id === chosen;
            const indicator = indicatorText(cause);
            return (
              <button
                key={cause.id}
                type="button"
                className={on ? "cause-tile cause-tile-on" : "cause-tile"}
                aria-pressed={on}
                onClick={() => setChosen(on ? null : cause.id)}
              >
                <h2>
                  <Icon name={CAUSE_ICONS[cause.id]} />
                  {CAUSE_TITLES[cause.id]}
                </h2>
                <p className="cause-finding">{cause.finding}</p>
                {indicator && (
                  <div className="cause-indicator">
                    <span className="eyebrow">{cause.indicator.name}</span>
                    <strong>{indicator}</strong>
                  </div>
                )}
                <span className="cause-foot">
                  Co mogę zrobić? <Chevron open={on} />
                </span>
              </button>
            );
          })}
        </section>
      )}
      {unjudged.length > 0 && (
        <p className="hint">
          Nie udało się ocenić: {unjudged.map((cause) => lowerPl(CAUSE_TITLES[cause.id])).join(", ")} (brak danych).
        </p>
      )}
      {open.map((cause) => (
        <CausePath key={cause.id} cause={cause} report={report} />
      ))}
    </>
  );
}

function CausePath({ cause, report }: { cause: Cause; report: Report }) {
  const [infoOpen, setInfoOpen] = useState(false);
  const sources = [...new Set(cause.facts.map((fact) => fact.source).filter(Boolean))];
  const citations = [...new Set(cause.recommendations.map((item) => item.citation).filter(Boolean))];
  const rules = [...new Set(cause.recommendations.map((item) => item.rule).filter(Boolean))];
  const indicator = indicatorText(cause);
  return (
    <section className="cause-path print-break">
      <div className="cause-path-head">
        <h2>
          <Icon name={CAUSE_ICONS[cause.id]} />
          {CAUSE_TITLES[cause.id]}
        </h2>
        <button
          type="button"
          className={infoOpen ? "info-button info-button-on no-print" : "info-button no-print"}
          aria-expanded={infoOpen}
          aria-label="Informacje o danych i obliczeniach"
          onClick={() => setInfoOpen(!infoOpen)}
        >
          i
        </button>
      </div>
      {infoOpen && (
        <dl className="cause-info">
          <dt>Skąd są dane</dt>
          <dd>{sources.join("; ") || "—"}</dd>
          <dt>Jak policzono</dt>
          <dd>
            {cause.indicator.name}
            {indicator ? `: ${indicator}` : ""}
            {rules.map((rule) => (
              <span key={rule}>Reguła rekomendacji: {rule}</span>
            ))}
          </dd>
          {citations.length > 0 && (
            <>
              <dt>Źródła zaleceń</dt>
              <dd>
                {citations.map((citation) => (
                  <span key={citation}>{citation}</span>
                ))}
              </dd>
            </>
          )}
        </dl>
      )}
      <div className="flow">
        <div className="flow-step">
          <p className="flow-title">
            <span>1</span>Przyczyna
          </p>
          <div className="flow-body">
            <p className="flow-main">{cause.finding}</p>
            {cause.facts.map((fact) => (
              <p key={fact.text} className="flow-fact">
                {fact.text}
              </p>
            ))}
            {(cause.id === "runoff" || cause.recommendations.some((item) => item.retention_site)) && (
              <ParcelSketch map={report.map} />
            )}
          </div>
        </div>
        <Arrow />
        <div className="flow-step">
          <p className="flow-title">
            <span>2</span>Zalecenia
          </p>
          <ul className="flow-body">
            {cause.recommendations.length === 0 && <li>Dla tej przyczyny nie mamy zalecenia.</li>}
            {cause.recommendations.map((item) => (
              <li key={item.id}>
                <small className="eyebrow">{item.group}</small>
                <span>{item.text}</span>
                {item.link === "simulation" && (
                  <Link to={`/raport/${report.meta.report_id}/symulacja`} className="no-print">
                    Porównaj uprawy (Symulacja)
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
        <Arrow />
        <div className="flow-step flow-step-dark">
          <p className="flow-title">
            <span>3</span>Efekt
          </p>
          <ul className="flow-body">
            {cause.recommendations.map((item) => (
              <li key={item.id}>{item.gain}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
