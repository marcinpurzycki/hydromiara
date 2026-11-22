import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Link, Navigate, useParams } from "react-router";
import type { Report } from "../api/types";
import { datePl, dateTimePl } from "../lib/format";
import { pdfFileName, saveElementAsPdf } from "../lib/report-pdf";
import { missingTopics } from "../lib/report-view";
import { useReport, type ReportLoad } from "../lib/use-report";
import { Causes } from "../report/Causes";
import { ExtraInfo, IrrigationCard } from "../report/ExtraInfo";
import { ReportActions } from "../report/ReportActions";
import { Verdicts } from "../report/Verdicts";
import type { StartPrefill } from "./StartScreen";

/** Screens shared by every route that needs a ready Report. */
export function ReportGate({ load, reportId }: { load: Exclude<ReportLoad, { state: "ready" }>; reportId: string }) {
  if (load.state === "loading") return <p className="screen screen-text lead">Wczytujemy raport…</p>;
  if (load.state === "running") return <Navigate to={`/analiza/${reportId}`} replace />;
  if (load.state === "unavailable") {
    return (
      <div className="screen screen-text">
        <h1>Nie udało się wczytać raportu</h1>
        <div role="alert" className="notice notice-warning">
          <b>{load.message}</b>
          <span>Raport nie zginął: jest zapisany pod tym adresem.</span>
        </div>
        <button type="button" className="button button-primary button-large" onClick={load.retry}>
          Spróbuj ponownie
        </button>
      </div>
    );
  }
  return (
    <div className="screen screen-text">
      <h1>{load.state === "missing" ? "Nie ma takiego raportu" : "Raport nie powstał"}</h1>
      <div role="alert" className="notice notice-warning">
        <b>{load.message}</b>
        {load.state === "missing" && (
          <span>Raporty są przechowywane przez 30 dni. Sprawdź adres albo uruchom analizę jeszcze raz.</span>
        )}
      </div>
      <Link to="/" className="button button-primary button-large">
        Nowa analiza
      </Link>
    </div>
  );
}

export const prefillOf = (report: Report): StartPrefill => ({
  parcelId: report.meta.parcel.parcel_id,
  cropId: report.meta.crop.id,
  analysisDate: report.meta.analysis_date,
});

export function ReportHeading({ report, title }: { report: Report; title: string }) {
  const { parcel, crop, analysis_date } = report.meta;
  return (
    <div>
      <h1 className="wrap-anywhere">
        {title} {parcel.parcel_id}
      </h1>
      <p className="lead">
        {crop.name}
        {parcel.region ? ` · ${parcel.region}` : ""} · Data analizy: {datePl(analysis_date)}
      </p>
    </div>
  );
}

export function ReportScreen() {
  const reportId = useParams().reportId ?? "";
  const load = useReport(reportId);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [extraOpen, setExtraOpen] = useState(false);
  const [allOpen, setAllOpen] = useState(false);
  const [printing, setPrinting] = useState(false);
  const page = useRef<HTMLDivElement>(null);

  // Printing shows the whole Report: every folded part is opened for the printout,
  // also when the user prints from the browser menu. flushSync makes the opened
  // parts exist before the browser takes the page for printing.
  useEffect(() => {
    const before = () => flushSync(() => setPrinting(true));
    const after = () => setPrinting(false);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  if (load.state !== "ready") return <ReportGate load={load} reportId={reportId} />;
  const report = load.report;
  const { meta, season } = report;
  const missing = missingTopics(report);
  const state = report.current_status.details.season_state;

  /** The file shows the whole Report, like the printout: every folded part is opened for it. */
  const savePdf = async () => {
    if (!page.current) return;
    flushSync(() => setPrinting(true));
    try {
      await saveElementAsPdf(
        page.current,
        pdfFileName(meta.parcel.parcel_id, meta.analysis_date),
        `Hydromiara · ${window.location.href} · wygenerowano ${dateTimePl(meta.created_at)}`,
      );
    } finally {
      setPrinting(false);
    }
  };

  return (
    <div className="screen screen-narrow report" ref={page}>
      <div>
        <h1 className="wrap-anywhere">Raport dla działki {meta.parcel.parcel_id}</h1>
        <p className="lead lead-row">
          <span>
            {meta.crop.name}
            {meta.parcel.region ? ` · ${meta.parcel.region}` : ""} · Data analizy: {datePl(meta.analysis_date)}
          </span>
          <Link to="/" state={{ prefill: prefillOf(report) }} className="link-button no-print">
            Zmień datę
          </Link>
        </p>
      </div>

      {meta.changed_from_date && (
        <div className="notice notice-plain">
          <b>Raport dla okresu największego zapotrzebowania na wodę</b>
          <i>Data analizy została zmieniona z {datePl(meta.changed_from_date)}.</i>
        </div>
      )}
      {(state === "out_of_season" || state === "dormant") && season.note && (
        <div className="notice notice-plain">
          <b>{state === "dormant" ? "Uprawa jest w spoczynku zimowym" : "Data analizy jest poza sezonem uprawy"}</b>
          <i>{season.note}</i>
        </div>
      )}
      {missing.length > 0 && (
        <div className="notice notice-warning">
          <b>{missing.length === 1 ? "Jedno ze źródeł nie dało danych" : "Część źródeł nie dała danych"}</b>
          <i>
            Brak danych: {missing.join(", ").toLocaleLowerCase("pl")}. Raport powstał z pozostałych danych, dlatego
            pewność oceny może być niższa.
          </i>
        </div>
      )}

      <section className="card summary print-section">
        <p className="summary-headline">{report.headline}</p>
        <p>{report.summary.text}</p>
        <p className="hint small">
          {report.summary.source === "llm"
            ? "Podsumowanie zredagował model językowy na podstawie wyniku obliczeń; liczby i oceny pochodzą z obliczeń."
            : "Podsumowanie z szablonu, na podstawie wyniku obliczeń."}
        </p>
      </section>

      <Verdicts
        report={report}
        historyOpen={historyOpen || printing}
        onToggleHistory={() => setHistoryOpen(!historyOpen)}
      />
      <Causes report={report} allOpen={allOpen || printing} />
      <IrrigationCard report={report} />
      <ExtraInfo report={report} open={extraOpen || printing} onToggle={() => setExtraOpen(!extraOpen)} />

      {meta.derived_from && (
        <p className="hint no-print">
          Ten raport powstał z innego raportu po zmianie Historii upraw.{" "}
          <Link to={`/raport/${meta.derived_from}`}>Otwórz raport źródłowy</Link>
        </p>
      )}
      <div className="print-footer">
        <span>Raport: {window.location.href}</span>
        <span>Wygenerowano: {dateTimePl(meta.created_at)}</span>
        <span>{window.location.host}</span>
      </div>
      <ReportActions
        allOpen={allOpen}
        onToggleAll={() => setAllOpen(!allOpen)}
        onPrint={() => window.print()}
        onPdf={savePdf}
      />
    </div>
  );
}
