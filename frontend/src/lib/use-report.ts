// Loading of one Report with the states the screens have to tell apart.
import { useEffect, useState } from "react";
import { ApiError, api, errorMessage } from "../api/client";
import type { Report } from "../api/types";

export type ReportLoad =
  | { state: "loading" }
  | { state: "ready"; report: Report }
  /** The analysis still runs: the progress screen is the place to wait. */
  | { state: "running" }
  | { state: "missing"; message: string }
  | { state: "failed"; message: string };

export function useReport(reportId: string): ReportLoad {
  const [load, setLoad] = useState<ReportLoad>({ state: "loading" });
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
        else setLoad({ state: "failed", message: errorMessage(error) });
      },
    );
    return () => {
      active = false;
    };
  }, [reportId]);
  return load;
}
