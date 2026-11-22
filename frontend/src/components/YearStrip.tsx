// Row of years: one coloured block per year with a label under it.

export type YearState = "deficit" | "ok" | "unknown";

export interface StripYear {
  key: number;
  label: string;
  state: YearState;
  partial?: boolean;
  description: string;
}

const STATE_TEXT: Record<YearState, string> = {
  deficit: "niedobór wody w sezonie",
  ok: "bez niedoboru wody w sezonie",
  unknown: "nie oceniono",
};

export function YearStrip({ years, small = false }: { years: StripYear[]; small?: boolean }) {
  return (
    <div className={small ? "year-strip year-strip-small" : "year-strip"}>
      {years.map((year) => (
        <div
          key={year.key}
          className="year-cell"
          role="img"
          aria-label={`${year.description}: ${STATE_TEXT[year.state]}${year.partial ? " (rok niepełny)" : ""}`}
        >
          <span className={`year-block year-${year.state}${year.partial ? " year-partial" : ""}`} />
          <span className="year-label">
            {year.label}
            {year.partial ? "*" : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

export function YearLegend({ unknown = false, partial = false }: { unknown?: boolean; partial?: boolean }) {
  return (
    <div className="year-legend">
      <span>
        <i className="year-deficit" />
        rok z niedoborem wody w sezonie
      </span>
      <span>
        <i className="year-ok" />
        rok bez niedoboru
      </span>
      {unknown && (
        <span>
          <i className="year-unknown" />
          rok nieoceniony
        </span>
      )}
      {partial && <span>* rok liczony tylko do Daty analizy</span>}
    </div>
  );
}
