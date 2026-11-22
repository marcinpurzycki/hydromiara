// Reading of a Report for display: states the contract expresses indirectly.
import type { Cause, CauseId, HistoricalYear, Irrigation, Report, Scalar } from "../api/types";
import { numberPl, rangePl } from "./format";

export const SCALE_LABELS = ["W normie", "Lekki niedobór", "Wyraźny niedobór", "Silny niedobór"];

export const TOPIC_LABELS: Record<string, string> = {
  parcel: "Działka",
  weather: "Pogoda",
  soil: "Gleba",
  terrain: "Ukształtowanie terenu",
  hydro: "Woda w okolicy",
  satellite: "Zdjęcia z satelity",
  drought_background: "Tło suszowe",
};

export const CAUSE_TITLES: Record<CauseId, string> = {
  precipitation: "Brak opadów",
  soil: "Słaba gleba",
  runoff: "Szybki odpływ",
  crop_demand: "Uprawa",
};

export const CAUSE_ICONS: Record<CauseId, "cloud" | "drop" | "waves" | "ear"> = {
  precipitation: "cloud",
  soil: "drop",
  runoff: "waves",
  crop_demand: "ear",
};

/** Level 0 means "w normie" only when the verdict was really assessed. */
export const currentAssessed = (report: Report) => report.current_status.details.assessed !== false;

export const multiyearAssessed = (report: Report) => report.multiyear_susceptibility.total_years > 0;

export const isBareField = (report: Report) => report.meta.crop.id === "bare_field";

export const foundCauses = (report: Report) => report.causes.filter((cause) => cause.found);

/** Causes that could not be judged for lack of data (not the same as "not found"). */
export const unjudgedCauses = (report: Report) =>
  report.causes.filter((cause) => !cause.found && cause.indicator.value === null);

export const yearNotAssessed = (year: HistoricalYear) =>
  (year.satellite_note ?? "").startsWith("Roku nie oceniono");

export const missingTopics = (report: Report) =>
  report.sources.filter((source) => source.missing).map((source) => TOPIC_LABELS[source.topic] ?? source.topic);

const NO_RECOMMENDATIONS =
  "Na tej działce nie stwierdzono niedoboru wody dla tej uprawy, więc nie przedstawiamy rekomendacji.";

/** Sentence shown instead of the cause tiles when the Report has no causes. */
export function noCausesSentence(report: Report): string {
  const fromReport = report.limitations.find((item) => item.affects === "recommendations" && !item.permanent);
  return fromReport?.text ?? NO_RECOMMENDATIONS;
}

export function indicatorText(cause: Cause): string | null {
  const { value, unit, threshold } = cause.indicator;
  if (value === null) return null;
  const withUnit = (number: number) => `${numberPl(number)}${unit ? ` ${unit}` : ""}`;
  return threshold === null ? withUnit(value) : `${withUnit(value)} (próg ${numberPl(threshold)})`;
}

const PENDING_REASON = "Uzasadnienie słowne nie jest jeszcze dostępne";

const DETAIL_LINES: [string, (value: number) => string][] = [
  ["depletion_pct", (v) => `Z zapasu wody dostępnego w glebie zużyte jest ${numberPl(v, 0)}%.`],
  ["stress_run_days", (v) => `Roślina pobiera mniej wody, niż potrzebuje, od ${numberPl(v, 0)} dni.`],
  ["precipitation_30d_mm", (v) => `W ostatnich 30 dniach spadło ${numberPl(v, 0)} mm deszczu.`],
  ["et0_30d_mm", (v) => `W tym czasie parowanie wskaźnikowe wyniosło ${numberPl(v, 0)} mm.`],
];

/** The reason of the current verdict; numbers stand in while the sentence is a placeholder. */
export function currentReason(report: Report): string {
  const { reason, details } = report.current_status;
  if (!reason.startsWith(PENDING_REASON)) return reason;
  const lines = DETAIL_LINES.flatMap(([key, text]) => {
    const value: Scalar | undefined = details[key];
    return typeof value === "number" ? [text(value)] : [];
  });
  return lines.length > 0 ? lines.join("\n") : reason;
}

export interface IrrigationCell {
  label: string;
  value: string;
  note: string;
}

/** The three cells of the irrigation panel; empty unless irrigation is justified. */
export function irrigationCells(irrigation: Irrigation): IrrigationCell[] {
  if (!irrigation.applicable || irrigation.justified !== true) return [];
  const cells: IrrigationCell[] = [
    { label: "Czy warto", value: "Tak", note: "W glebie jest mniej wody, niż uprawa teraz potrzebuje." },
  ];
  if (irrigation.amount_mm) {
    const perHectare = irrigation.amount_m3_ha ? `czyli ${rangePl(irrigation.amount_m3_ha)} m³ na hektar` : "";
    cells.push({ label: "Ile wody", value: `${rangePl(irrigation.amount_mm)} mm`, note: perHectare });
  }
  if (irrigation.timing) cells.push({ label: "Kiedy", value: "", note: irrigation.timing });
  return cells;
}

export function traceValues(values: Record<string, Scalar>): string {
  return Object.entries(values)
    .map(([key, value]) => `${key} = ${typeof value === "number" ? numberPl(value, 3) : String(value)}`)
    .join("; ");
}
