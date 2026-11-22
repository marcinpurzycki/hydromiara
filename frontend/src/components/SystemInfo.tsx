import { useEffect, useRef, useState } from "react";
import {
  DERIVED_SOURCES,
  DIRECTIONS,
  INTRO,
  LIVE_SOURCES,
  REFERENCES,
  TRANSPARENCY,
  type InfoSource,
} from "../lib/system-info";
import { Icon } from "./Icon";

function SourceTable({ sources }: { sources: InfoSource[] }) {
  return (
    <div className="table-scroll">
      <table className="info-table">
        <thead>
          <tr>
            <th>Źródło</th>
            <th>Jakie dane bierzemy</th>
            <th>Do czego służą</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.name}>
              <th scope="row">{source.name}</th>
              <td>{source.data}</td>
              <td>{source.use}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Button on the start screen and the window that explains the system. */
export function SystemInfo() {
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);

  return (
    <>
      <button type="button" className="button button-outline no-print" onClick={() => setOpen(true)}>
        <Icon name="info" size={24} />
        O systemie
      </button>
      {open && (
        <dialog
          ref={dialog}
          className="info-dialog"
          aria-labelledby="info-title"
          onClose={() => setOpen(false)}
          onClick={(event) => {
            // a click on the backdrop lands on the dialog element itself
            if (event.target === event.currentTarget) event.currentTarget.close();
          }}
        >
          <div className="info-body">
            <div className="info-head">
              <h2 id="info-title">O systemie Hydromiara</h2>
              <button type="button" className="button button-soft button-small" onClick={() => dialog.current?.close()}>
                Zamknij
              </button>
            </div>

            <section>
              <h3>Co robi system</h3>
              <p>{INTRO}</p>
            </section>

            <section>
              <h3>Dane publiczne czytane dla każdej działki</h3>
              <p className="hint">
                Pobierane na bieżąco w trakcie analizy, z usług instytucji publicznych i programów europejskich.
              </p>
              <SourceTable sources={LIVE_SOURCES} />
            </section>

            <section>
              <h3>Wartości z literatury naukowej i z badań zespołu</h3>
              <p className="hint">
                Metoda, parametry upraw i progi, wpisane w systemie ze wskazaniem źródła. Nie są pobierane.
              </p>
              <SourceTable sources={DERIVED_SOURCES} />
            </section>

            <section className="info-note">
              <h3>Każdy wynik da się sprawdzić</h3>
              <p>{TRANSPARENCY}</p>
            </section>

            <section>
              <h3>Źródła naukowe</h3>
              <ul className="info-references">
                {REFERENCES.map((reference) => (
                  <li key={reference}>{reference}</li>
                ))}
              </ul>
            </section>

            <section className="info-directions">
              <h2>Możliwości rozwoju</h2>
              {DIRECTIONS.map((direction) => (
                <div key={direction.title} className="info-direction">
                  <h3>{direction.title}</h3>
                  <p>{direction.text}</p>
                  <p className="info-direction-note">{direction.note}</p>
                </div>
              ))}
            </section>
          </div>
        </dialog>
      )}
    </>
  );
}
