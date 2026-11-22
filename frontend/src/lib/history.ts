// Crop history form: the draft, its filling rule and the request body.
import type { CropHistory } from "../api/types";

export const WINDOW_LENGTH = 10;

/** Years offered before the Report exists: ten years ending with the analysis year. */
export function defaultWindow(analysisDate: string): number[] {
  const last = Number(analysisDate.slice(0, 4));
  return Array.from({ length: WINDOW_LENGTH }, (_, index) => last - WINDOW_LENGTH + 1 + index);
}

/**
 * Draft of the form, oldest year first. `crops[i]` is a crop identifier or "".
 * `filledFrom[i]` is the index of the newer year a value was copied from, or
 * null when the user chose the value (or the year is empty).
 */
export interface HistoryDraft {
  crops: string[];
  filledFrom: (number | null)[];
}

export function emptyDraft(length: number): HistoryDraft {
  return { crops: Array(length).fill(""), filledFrom: Array(length).fill(null) };
}

/**
 * A crop chosen for a year also fills the older years, up to the nearest year
 * the user set by hand. Clearing a year clears only the years filled from it.
 */
export function chooseCrop(draft: HistoryDraft, index: number, cropId: string): HistoryDraft {
  const crops = [...draft.crops];
  const filledFrom = [...draft.filledFrom];
  crops[index] = cropId;
  filledFrom[index] = null;
  for (let older = index - 1; older >= 0; older--) {
    if (cropId === "") {
      if (filledFrom[older] === index) {
        crops[older] = "";
        filledFrom[older] = null;
      }
      continue;
    }
    if (crops[older] !== "" && filledFrom[older] === null) break;
    crops[older] = cropId;
    filledFrom[older] = index;
  }
  return { crops, filledFrom };
}

export const givenCount = (draft: HistoryDraft) => draft.crops.filter(Boolean).length;

/** Request body: only the years the user filled in. */
export function historyOfDraft(years: number[], draft: HistoryDraft): CropHistory {
  const given: Record<string, string> = {};
  years.forEach((year, index) => {
    if (draft.crops[index]) given[String(year)] = draft.crops[index];
  });
  return { years: given };
}

/** A history limited to the given years; other forms pass unchanged. */
export function limitedTo(history: CropHistory, allowed: number[]): CropHistory {
  if (!("years" in history)) return history;
  const keep = new Set(allowed.map(String));
  return { years: Object.fromEntries(Object.entries(history.years).filter(([year]) => keep.has(year))) };
}

/** Years of the window named by the API in its refusal, e.g. "(2013–2022)". */
export function windowFromMessage(message: string): number[] | null {
  const found = /\((\d{4})–(\d{4})\)/.exec(message);
  if (!found) return null;
  const first = Number(found[1]);
  const last = Number(found[2]);
  if (last < first || last - first > 40) return null;
  return Array.from({ length: last - first + 1 }, (_, index) => first + index);
}

// A history the API could not take during the analysis waits here until the
// Report is ready and is then sent as a derived report.
const pendingKey = (reportId: string) => `hydromiara:history:${reportId}`;

export function storePending(reportId: string, history: CropHistory | null): void {
  try {
    if (history) sessionStorage.setItem(pendingKey(reportId), JSON.stringify(history));
    else sessionStorage.removeItem(pendingKey(reportId));
  } catch {
    // Storage switched off: the answer is simply not carried over.
  }
}

export function readPending(reportId: string): CropHistory | null {
  try {
    const raw = sessionStorage.getItem(pendingKey(reportId));
    return raw ? (JSON.parse(raw) as CropHistory) : null;
  } catch {
    return null;
  }
}
