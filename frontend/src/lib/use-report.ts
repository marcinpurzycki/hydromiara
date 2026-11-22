// Loading of one Report with the states the screens have to tell apart.
import { useEffect, useState } from "react";
import { ApiError, api, errorMessage, isAnalysisFailure } from "../api/client";
import type { Report } from "../api/types";

export type ReportLoad =
  | { state: "loading" }
  | { state: "ready"; report: Report }
  /** The analysis still runs: the progress screen is the place to wait. */
  | { state: "running" }
  | { state: "missing"; message: string }
  /** The analysis ended without a Report. */
  | { state: "failed"; message: string }
  /** The Report could not be fetched now; `retry` asks again. */
  | { state: "unavailable"; message: string; retry: () => void };

export function useReport(reportId: string): ReportLoad {
  const [load, setLoad] = useState<ReportLoad>({ state: "loading" });
  const [turn, setTurn] = useState(0);
  useEffect(() => {
    let active = true;
    setLoad({ state: "loading" });
    api.report(reportId).then(
      (report) => active && setLoad({ state: "ready", report }),
      (error) => {
        if (!active) return;
        const code = error instanceof ApiError ? error.code : "";
        if (code === "report_not_ready") setLoad({ state: "running" });
        else if (code === "report_not_found") setLoad({ state: "missing", message: errorMessage(error) });
        else if (isAnalysisFailure(error)) setLoad({ state: "failed", message: errorMessage(error) });
        else setLoad({ state: "unavailable", message: errorMessage(error), retry: () => setTurn((n) => n + 1) });
      },
    );
    return () => {
      active = false;
    };
  }, [reportId, turn]);
  return load;
}
