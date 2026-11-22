// Progress of one analysis: polling, failure reason, crop history answer.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage, sleep } from "../api/client";
import type { AnalysisStatus, CropHistory } from "../api/types";
import { limitedTo, readPending, storePending, windowFromMessage } from "../lib/history";

const POLL_MS = 1000;
const NO_HISTORY: CropHistory = { years: {} };

export interface AnalysisProgress {
  status: AnalysisStatus | null;
  /** Message of a failed analysis or of a report that does not exist. */
  failure: string | null;
  missingReport: boolean;
  sendHistory: (history: CropHistory | null) => void;
  /** Address of the Report to open once the analysis is done. */
  openReport: () => Promise<string>;
}

export function useAnalysis(reportId: string): AnalysisProgress {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [missingReport, setMissingReport] = useState(false);
  const finished = useRef(false);
  const sending = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    let active = true;
    finished.current = false;
    const poll = async () => {
      while (active) {
        try {
          const current = await api.status(reportId);
          if (!active) return;
          setStatus(current);
          if (current.state !== "running") {
            finished.current = true;
            if (current.state === "failed") {
              // The progress route does not carry the reason; the report route does.
              const reason = await api.report(reportId).then(
                () => null,
                (error) => errorMessage(error),
              );
              if (active) setFailure(reason ?? "Analiza nie powiodła się. Spróbuj ponownie.");
            }
            return;
          }
        } catch (error) {
          if (!active) return;
          if (error instanceof ApiError && error.code === "report_not_found") {
            setMissingReport(true);
            setFailure(error.message);
            return;
          }
          if (error instanceof ApiError && error.retryAfterS) await sleep(error.retryAfterS * 1000);
        }
        await sleep(POLL_MS);
      }
    };
    void poll();
    return () => {
      active = false;
    };
  }, [reportId]);

  const sendHistory = useCallback(
    (history: CropHistory | null) => {
      const body = history ?? NO_HISTORY;
      const put = async (attempt: CropHistory): Promise<void> => {
        try {
          await api.putHistory(reportId, attempt);
          storePending(reportId, null);
        } catch (error) {
          const code = error instanceof ApiError ? error.code : "";
          const window = code === "crop_history_year_outside_window" ? windowFromMessage(errorMessage(error)) : null;
          if (window && attempt === body) return put(limitedTo(body, window));
          // Too late or not accepted now: it goes into a derived report later.
          storePending(reportId, code === "crop_history_not_applicable" ? null : history);
        }
      };
      if (finished.current) storePending(reportId, history);
      else sending.current = put(body);
    },
    [reportId],
  );

  const openReport = useCallback(async () => {
    // An answer still on its way decides whether a derived report is needed.
    await sending.current;
    const pending = readPending(reportId);
    if (!pending) return `/raport/${reportId}`;
    storePending(reportId, null);
    try {
      const report = await api.report(reportId);
      const years = report.multiyear_susceptibility.years.map((year) => year.year);
      const derived = await api.derive(reportId, limitedTo(pending, years));
      return `/raport/${derived.report_id}`;
    } catch {
      return `/raport/${reportId}`;
    }
  }, [reportId]);

  return { status, failure, missingReport, sendHistory, openReport };
}
