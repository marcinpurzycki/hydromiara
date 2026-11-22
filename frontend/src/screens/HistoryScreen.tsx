import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, errorMessage } from "../api/client";
import type { CropHistory, Report } from "../api/types";
import { HistoryForm } from "../components/HistoryForm";
import { useCrops } from "../lib/catalog";
import { defaultWindow, emptyDraft, givenCount, historyOfDraft, type HistoryDraft } from "../lib/history";
import { isBareField } from "../lib/report-view";
import { useReport } from "../lib/use-report";
import { ReportGate, ReportHeading } from "./ReportScreen";

/** Years of the form: the multi-year window of the Report, or ten years when it is unknown. */
function windowOf(report: Report): number[] {
  const assessed = report.multiyear_susceptibility.years.map((year) => year.year);
  const named = (report.historical_course?.years ?? []).map((year) => year.year);
  const known = [...assessed, ...named];
  if (known.length === 0) return defaultWindow(report.meta.analysis_date);
  const first = Math.min(...known);
  return Array.from({ length: Math.max(...known) - first + 1 }, (_, index) => first + index);
}

/** The form starts from the history the Report already has: years with another crop. */
function draftOf(report: Report, years: number[]): HistoryDraft {
  const draft = emptyDraft(years.length);
  for (const year of report.historical_course?.years ?? []) {
    const index = years.indexOf(year.year);
    if (index >= 0 && year.crop.id !== report.meta.crop.id) draft.crops[index] = year.crop.id;
  }
  return draft;
}

export function HistoryScreen() {
  const reportId = useParams().reportId ?? "";
  const navigate = useNavigate();
  const load = useReport(reportId);
  const { crops } = useCrops();
  const report = load.state === "ready" ? load.report : null;
  const [years, setYears] = useState<number[]>([]);
  const [draft, setDraft] = useState<HistoryDraft>(emptyDraft(0));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!report) return;
    const window = windowOf(report);
    setYears(window);
    setDraft(draftOf(report, window));
  }, [report]);

  if (load.state !== "ready") return <ReportGate load={load} reportId={reportId} />;
  if (!report) return null;
  const back = `/raport/${reportId}`;

  if (isBareField(report)) {
    return (
      <div className="screen screen-text">
        <ReportHeading report={report} title="Historia upraw na działce" />
        <div className="notice notice-plain">
          <b>Ten raport dotyczy pola bez uprawy, więc historii upraw się dla niego nie podaje.</b>
        </div>
        <Link to={back} className="button button-primary button-large">
          Wróć do raportu
        </Link>
      </div>
    );
  }

  const save = async (history: CropHistory) => {
    setSaving(true);
    setError(null);
    try {
      const derived = await api.derive(reportId, history);
      navigate(`/raport/${derived.report_id}`);
    } catch (failure) {
      setError(errorMessage(failure));
      setSaving(false);
    }
  };

  const given = givenCount(draft);
  return (
    <div className="screen screen-narrow">
      <ReportHeading report={report} title="Historia upraw na działce" />
      <p className="text-column">
        Wybierz, co rosło na działce w każdym z lat przed Datą analizy. Nie musisz wypełniać wszystkiego: lata
        puste liczymy „jak obecnie”, czyli tak, jakby rosła wtedy obecna uprawa.
      </p>
      <section className="card history-card">
        <HistoryForm
          years={years}
          draft={draft}
          crops={crops}
          currentCropName={report.meta.crop.name}
          wide
          onChange={setDraft}
        />
        <p className="hint" aria-live="polite">
          Historia upraw podana dla {given} z {years.length} lat.
        </p>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <div className="button-row">
          <button
            type="button"
            className="button button-primary button-large"
            disabled={saving}
            onClick={() => void save(historyOfDraft(years, draft))}
          >
            {saving ? "Zapisujemy…" : "Zapisz i pokaż raport"}
          </button>
          <Link to={back} className="link-button">
            Wróć do raportu bez zmian
          </Link>
          {report.historical_course && (
            <button type="button" className="link-button" disabled={saving} onClick={() => void save({ years: {} })}>
              Usuń historię upraw
            </button>
          )}
        </div>
      </section>
      <div className="notice notice-plain text-column">
        <b>Co się zmieni w raporcie</b>
        <span>
          Po zapisaniu powstanie nowy raport z tych samych danych źródłowych, pod nowym adresem. Oceny, przyczyny
          i rekomendacje zostają takie same. Dojdzie wiersz „Co faktycznie rosło”: jakie uprawy tu były i czy
          brakowało im wody.
        </span>
      </div>
    </div>
  );
}
