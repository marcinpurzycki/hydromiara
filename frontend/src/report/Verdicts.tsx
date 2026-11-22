import { Link } from "react-router";
import type { Report } from "../api/types";
import { Chevron } from "../components/Icon";
import { YearLegend, YearStrip, type StripYear } from "../components/YearStrip";
import { cropAbbreviation, datePl, lowerPl, twoDigitYear } from "../lib/format";
import {
  SCALE_LABELS,
  currentAssessed,
  currentReason,
  isBareField,
  multiyearAssessed,
  multiyearNotAssessedLabel,
  stateDay,
  yearNotAssessed,
} from "../lib/report-view";

interface Props {
  report: Report;
  historyOpen: boolean;
  onToggleHistory: () => void;
}

/** The two verdicts: the current water situation and the multi-year susceptibility. */
export function Verdicts({ report, historyOpen, onToggleHistory }: Props) {
  const current = report.current_status;
  const assessed = currentAssessed(report);
  const label = current.label.charAt(0).toLocaleUpperCase("pl") + current.label.slice(1);
  const day = stateDay(report);
  return (
    <section aria-label="Ocena" className="card verdicts print-section">
      <div className="verdict">
        <p className="eyebrow">Bieżąca sytuacja wodna{day ? ` · stan na koniec dnia ${datePl(day)}` : ""}</p>
        <div className="verdict-grid">
          <div>
            <p className={assessed ? `status status-${current.deficit_level}` : "status status-none"}>{label}</p>
            <p className="reason">{currentReason(report)}</p>
          </div>
          <div className="scale" aria-hidden="true">
            {SCALE_LABELS.map((text, level) => {
              const on = assessed && level === current.deficit_level;
              return (
                <div key={text} className={on ? "scale-step scale-on" : "scale-step"}>
                  <span className={`scale-bar level-${level}`} />
                  <span className="scale-label">{text}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="verdict-foot">
          <p className="hint">
            Pewność oceny: {current.confidence.level} – {current.confidence.why}
          </p>
          <button
            type="button"
            className="button button-soft no-print"
            aria-expanded={historyOpen}
            onClick={onToggleHistory}
          >
            {historyOpen ? "Ukryj historię" : "Pokaż historię"}
            <Chevron open={historyOpen} />
          </button>
        </div>
      </div>
      {historyOpen && <Multiyear report={report} />}
    </section>
  );
}

function Multiyear({ report }: { report: Report }) {
  const multi = report.multiyear_susceptibility;
  const course = report.historical_course;
  const years: StripYear[] = multi.years.map((year) => ({
    key: year.year,
    label: twoDigitYear(year.year),
    state: year.deficit ? "deficit" : "ok",
    partial: year.partial,
    description: String(year.year),
  }));
  const grown: StripYear[] = (course?.years ?? []).map((year) => ({
    key: year.year,
    label: cropAbbreviation(year.crop.name),
    state: yearNotAssessed(year) ? "unknown" : year.deficit ? "deficit" : "ok",
    description: `${year.year}, ${year.crop.name}`,
  }));
  const legend = [...new Map((course?.years ?? []).map((year) => [year.crop.id, year.crop.name])).values()];
  const first = multi.years[0]?.year;
  const last = multi.years[multi.years.length - 1]?.year;

  return (
    <div className="verdict verdict-second">
      <p className="eyebrow">Podatność wieloletnia{first ? ` · lata ${first}–${last}` : ""}</p>
      {multiyearAssessed(report) ? (
        <div className="verdict-grid">
          <div>
            <strong className="years-count">
              Wody brakowało w {multi.deficit_years} z {multi.total_years} lat
            </strong>
            <p className="reason">
              Stopień niedoboru w perspektywie wieloletniej: {lowerPl(SCALE_LABELS[multi.deficit_level])}.
              {multi.typical_period ? ` Najczęściej: ${multi.typical_period}.` : ""}
            </p>
            {course && <p className="hint">{course.comparison_sentence}</p>}
          </div>
          <div className="strips">
            {course && <p className="strip-title">Gdyby co roku rosła tu obecna uprawa</p>}
            <YearStrip years={years} />
            {course && (
              <>
                <p className="strip-title">Co faktycznie rosło</p>
                <YearStrip years={grown} />
                <p className="hint small">
                  {legend.map((name) => `${cropAbbreviation(name)} – ${lowerPl(name)}`).join(" · ")}
                </p>
              </>
            )}
            <YearLegend
              unknown={grown.some((year) => year.state === "unknown")}
              partial={years.some((year) => year.partial)}
            />
          </div>
        </div>
      ) : (
        <p className="status status-none">{multiyearNotAssessedLabel(report)}</p>
      )}
      <div className="verdict-foot">
        <p className="hint">
          Pewność oceny: {multi.confidence.level} – {multi.confidence.why}
        </p>
        <div className="history-note hint">
          <span>{multi.history_assumption}</span>
          {!isBareField(report) && (
            <Link to={`/raport/${report.meta.report_id}/historia`} className="button button-soft button-small no-print">
              {course ? "Zmień" : "Uzupełnij historię"}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
