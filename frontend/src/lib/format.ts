// Formatting of dates, numbers and names for display.

const pad = (value: number) => String(value).padStart(2, "0");

export function toIso(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export const todayIso = () => toIso(new Date());

/** The same day the given number of years before an ISO date. */
export function yearsBefore(iso: string, years: number): string {
  return `${Number(iso.slice(0, 4)) - years}${iso.slice(4)}`;
}

/** 2023-06-20 → 20.06.2023 */
export function datePl(iso: string): string {
  return iso.slice(0, 10).split("-").reverse().join(".");
}

export function dateTimePl(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(parsed);
}

export function numberPl(value: number, maxDigits = 2): string {
  return new Intl.NumberFormat("pl-PL", { maximumFractionDigits: maxDigits }).format(value);
}

export function rangePl(range: [number, number]): string {
  return `${numberPl(range[0], 0)}–${numberPl(range[1], 0)}`;
}

export const lowerPl = (text: string) => text.toLocaleLowerCase("pl");

export const twoDigitYear = (year: number) => String(year).slice(-2);

/** Short mark of a crop for the year strip: "Pszenica ozima" → "PO", "Żyto" → "ŻY". */
export function cropAbbreviation(name: string): string {
  const words = name.split(/[\s-]+/).filter((word) => /^\p{L}/u.test(word));
  if (words.length === 0) return "—";
  const letters = words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0];
  return letters.toLocaleUpperCase("pl");
}

/** Geographic coordinates shortened to about 10 m for display. */
export function coordinatesPl(lat: number, lon: number): string {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}
