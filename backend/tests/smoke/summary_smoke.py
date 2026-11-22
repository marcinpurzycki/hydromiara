"""Smoke check of the Report summary on live analyses (needs network).

Run from the backend directory:
    python -m tests.smoke.summary_smoke [PARCEL_ID [CROP_ID [ANALYSIS_DATE ...]]]

Runs one analysis per date and prints the summary stored in the Report, where
it came from, why the template was used if it was, and the template summary of
the same Report for comparison. With a configured provider (AI_API_KEY and
OPENAI_MODEL in the environment) every analysis makes exactly one call to the
language model; without one the template is the summary. The key and the model
name are not printed. Exits with 1 when an analysis fails or the stored
summary is empty.
"""

import sys
import time

from app.contracts.report import Report
from app.orchestrator.params import ANALYSIS_BUDGET_S
from app.summary.config import provider_config
from app.summary.service import RULE_ID
from app.summary.template import template_text
from tests.smoke.analysis_smoke import api_client

DEFAULTS = ("040704_2.0020.34/2", "winter_wheat", "2023-06-20", "2023-08-31")


def run(client, parcel_id: str, crop_id: str, analysis_date: str) -> bool:
    request = {"parcel_id": parcel_id, "crop_id": crop_id, "analysis_date": analysis_date}
    started = time.monotonic()
    response = client.post("/api/analyses", json=request)
    if response.status_code != 202:
        print(f"NOT ACCEPTED: {response.status_code} {response.text}")
        return False
    report_id = response.json()["report_id"]
    while True:
        status = client.get(f"/api/analyses/{report_id}/status").json()
        if status["state"] != "running" or time.monotonic() - started > 2 * ANALYSIS_BUDGET_S:
            break
        time.sleep(0.1)
    total_s = time.monotonic() - started
    answer = client.get(f"/api/reports/{report_id}")
    if answer.status_code != 200:
        print(f"NO REPORT: {answer.status_code} {answer.text}")
        return False
    report = Report.model_validate(answer.json())
    entry = next((item for item in report.trace if item.rule_id == RULE_ID), None)
    reason = None if entry is None else entry.values["fallback_reason"]
    print(f"\n=== {crop_id} {analysis_date}: state {status['state']}, total {total_s:.1f} s")
    print(f"summary source: {report.summary.source}; fallback reason: {reason}")
    print(f"summary ({len(report.summary.text)} characters):\n{report.summary.text}")
    if report.summary.source == "llm":
        print(f"template of the same Report:\n{template_text(report)}")
    return bool(report.summary.text.strip()) and total_s <= ANALYSIS_BUDGET_S


def main() -> int:
    arguments = sys.argv[1:]
    parcel_id = arguments[0] if arguments else DEFAULTS[0]
    crop_id = arguments[1] if len(arguments) > 1 else DEFAULTS[1]
    dates = arguments[2:] or DEFAULTS[2:]
    print(f"provider configured: {provider_config() is not None}")
    with api_client(None) as client:
        results = [run(client, parcel_id, crop_id, analysis_date) for analysis_date in dates]
    print("\nOK" if all(results) else "\nFAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
