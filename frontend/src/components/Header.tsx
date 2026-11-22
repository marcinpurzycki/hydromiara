import { Link, useLocation } from "react-router";

const STEPS = ["Działka", "Analiza", "Raport"];

interface Place {
  step: number;
  reportPath: string | null;
  onReport: boolean;
}

function placeOf(pathname: string): Place {
  const analysis = /^\/analiza\/[^/]+/.test(pathname);
  const report = /^\/raport\/([^/]+)(\/.*)?$/.exec(pathname);
  if (analysis) return { step: 2, reportPath: null, onReport: false };
  if (report) return { step: 3, reportPath: `/raport/${report[1]}`, onReport: !report[2] };
  return { step: 1, reportPath: null, onReport: false };
}

/** Where a step leads from the current screen; null when it is not a link. */
function target(step: number, place: Place): string | null {
  if (step === 1) return place.step === 1 ? null : "/";
  if (!place.reportPath) return null;
  if (step === 2) return `${place.reportPath}/historia`;
  return place.onReport ? null : place.reportPath;
}

const TITLES = ["Wróć do wyboru działki", "Zmień historię upraw", "Wróć do raportu"];

export function Header() {
  const place = placeOf(useLocation().pathname);
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Link to="/" className="logo-link">
          <img src="/logo-dark.svg" alt="Hydromiara – strona startowa" />
        </Link>
        <ol className="steps no-print" aria-label="Etapy">
          {STEPS.map((label, index) => {
            const step = index + 1;
            const state = step === place.step ? "current" : step < place.step ? "past" : "next";
            const to = target(step, place);
            const body = (
              <>
                <span className="step-number">{state === "past" ? "✓" : step}</span>
                <span className="step-label">{label}</span>
              </>
            );
            return (
              <li key={label} className={`step step-${state}`}>
                {index > 0 && <span className="step-line" />}
                {to ? (
                  <Link to={to} className="step-body step-link" title={TITLES[index]}>
                    {body}
                  </Link>
                ) : (
                  <span className="step-body" aria-current={state === "current" ? "step" : undefined}>
                    {body}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </header>
  );
}
