import { useState } from "react";
import type { Report } from "../api/types";
import { Chevron, Icon } from "../components/Icon";
import { datePl } from "../lib/format";
import { TOPIC_LABELS, irrigationCells, traceValues } from "../lib/report-view";

/** Irrigation is always shown: its text also says why there is no advice. */
export function IrrigationCard({ report }: { report: Report }) {
  const irrigation = report.irrigation;
  const cells = irrigationCells(irrigation);
  const season = report.season.last_season;
  return (
    <section className="card irrigation print-section">
      <h2 className="card-title">
        <Icon name="sprout" />
        Nawadnianie
      </h2>
      <div className="irrigation-grid">
        <div>
          <p className="irrigation-main">{irrigation.text}</p>
          {!irrigation.applicable && season && (
            <p>
              Ostatni sezon uprawy: od {datePl(season.start)} do {datePl(season.end)}.
            </p>
          )}
          {cells.length > 0 && (
            <p className="hint">
              Zakres i termin wynikają ze stanu na Datę analizy. Nie uwzględniają prognozy pogody: jeśli spadnie
              deszcz, potrzebna dawka będzie mniejsza.
            </p>
          )}
        </div>
        {cells.length > 0 && (
          <dl className="irrigation-cells">
            {cells.map((cell) => (
              <div key={cell.label}>
                <dt>{cell.label}</dt>
                {cell.value && <dd className="cell-value">{cell.value}</dd>}
                <dd className="cell-note">{cell.note}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  );
}

interface ExtraProps {
  report: Report;
  open: boolean;
  onToggle: () => void;
}

/** Limitations, data sources, consistency check and the decision trace. */
export function ExtraInfo({ report, open, onToggle }: ExtraProps) {
  const [traceOpen, setTraceOpen] = useState(false);
  const check = report.consistency_check;
  return (
    <div className="card extra print-section">
      <button type="button" className="extra-toggle" aria-expanded={open} onClick={onToggle}>
        Dodatkowe informacje
        <Chevron open={open} />
      </button>
      {open && (
        <div className="extra-body">
          <section>
            <h3>Ograniczenia raportu</h3>
            <ul className="limitations">
              {report.limitations.map((item) => (
                <li key={item.text}>{item.text}</li>
              ))}
            </ul>
          </section>
          <section>
            <h3>Z czego to policzyliśmy</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Temat</th>
                    <th>Źródło</th>
                    <th>Dane z okresu</th>
                    <th>Tryb</th>
                    <th>Licencja</th>
                  </tr>
                </thead>
                <tbody>
                  {report.sources.map((source) => (
                    <tr key={source.topic} className={source.missing ? "row-missing" : undefined}>
                      <th scope="row">{TOPIC_LABELS[source.topic] ?? source.topic}</th>
                      <td>
                        {source.name}
                        {!source.missing && source.chain_step > 1 ? " (źródło zastępcze)" : ""}
                      </td>
                      <td>{source.missing ? "nie uwzględniono" : (source.data_date ?? "—")}</td>
                      <td>
                        {source.mode}
                        {source.fetched_at ? `, pobrano ${datePl(source.fetched_at)}` : ""}
                      </td>
                      <td>{source.license}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section>
            <h3>Sprawdzenie zgodności: {check.result}</h3>
            <p>{check.sentence}</p>
            {check.items.length > 0 && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Źródło</th>
                      <th>Okres</th>
                      <th>Wartość</th>
                      <th>Znaczenie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {check.items.map((item) => (
                      <tr key={`${item.source}${item.period}`}>
                        <th scope="row">{item.source}</th>
                        <td>{item.period}</td>
                        <td>{item.value}</td>
                        <td>{item.meaning}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          {report.trace.length > 0 && (
            <section className={traceOpen ? undefined : "no-print"}>
              <button
                type="button"
                className="link-button"
                aria-expanded={traceOpen}
                onClick={() => setTraceOpen(!traceOpen)}
              >
                {traceOpen ? "Ukryj ślad decyzji" : `Pokaż ślad decyzji (${report.trace.length} kroków)`}
              </button>
              {traceOpen && (
                <ol className="trace">
                  {report.trace.map((entry, index) => (
                    <li key={`${entry.rule_id}${index}`}>
                      <b>{entry.rule_id}</b>
                      <span>{entry.condition}</span>
                      {Object.keys(entry.values).length > 0 && <code>{traceValues(entry.values)}</code>}
                      <span>→ {entry.result}</span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          )}
          <p className="hint">
            Ten raport jest zapisany pod własnym adresem i się nie zmienia. Zmiana Daty analizy, uprawy albo
            Historii upraw tworzy nowy raport.
          </p>
        </div>
      )}
    </div>
  );
}
