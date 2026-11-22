"""Smoke check of an off-season Report and the critical-period analysis, live (needs network).

Run from the backend directory:
    python -m tests.smoke.season_smoke [PARCEL_ID [CROP_ID [ANALYSIS_DATE]]]
    python -m tests.smoke.season_smoke --url http://127.0.0.1:8000 [...]

Runs one analysis (by default winter wheat on a day of its dormancy), prints
the season section, the current water status and the irrigation text, then
asks for the critical-period analysis of that Report and prints what the new
Report says. Exits with 1 when an analysis fails, the new date is later than
the first one, the new Report does not name the first date, or the first
Report changed.
"""

import argparse
import sys
import time

from app.contracts.report import Report
from app.orchestrator.params import ANALYSIS_BUDGET_S
from tests.smoke.analysis_smoke import api_client

DEFAULTS = ("040704_2.0020.34/2", "winter_wheat", "2026-11-21")


def wait(client, report_id: str) -> tuple[bytes, Report] | None:
    """The stored Report of the analysis, raw and parsed; None when there is none."""
    started = time.monotonic()
    while True:
        status = client.get(f"/api/analyses/{report_id}/status").json()
        if status["state"] != "running" or time.monotonic() - started > 2 * ANALYSIS_BUDGET_S:
            break
        time.sleep(0.1)
    print(f"state {status['state']} after {time.monotonic() - started:.2f} s")
    answer = client.get(f"/api/reports/{report_id}")
    if answer.status_code != 200:
        print(f"NO REPORT: {answer.status_code} {answer.text}")
        return None
    return answer.content, Report.model_validate(answer.json())


def show(report: Report) -> None:
    current = report.current_status
    print(f"analysis date: {report.meta.analysis_date} "
          f"(changed from {report.meta.changed_from_date})")
    print(f"headline: {report.headline}")
    print(f"season: {report.season.model_dump_json()}")
    print(f"current: level {current.deficit_level}, label: {current.label}")
    print(f"reason: {current.reason}")
    print(f"confidence: {current.confidence.level}")
    print(f"irrigation: applicable={report.irrigation.applicable}; {report.irrigation.text}")
    print(f"consistency: {report.consistency_check.sentence}")


def run(client, parcel_id: str, crop_id: str, analysis_date: str) -> bool:
    request = {"parcel_id": parcel_id, "crop_id": crop_id, "analysis_date": analysis_date}
    response = client.post("/api/analyses", json=request)
    if response.status_code != 202:
        print(f"NOT ACCEPTED: {response.status_code} {response.text}")
        return False
    first_id = response.json()["report_id"]
    first = wait(client, first_id)
    if first is None:
        return False
    show(first[1])

    print("--- critical period ---")
    response = client.post(f"/api/reports/{first_id}/critical-period")
    print(f"answer: {response.status_code} {response.text}")
    if response.status_code != 202:
        # A Report already on the middle day, or the field without a crop.
        return response.status_code == 409
    body = response.json()
    second = wait(client, body["report_id"])
    if second is None:
        return False
    show(second[1])
    unchanged = client.get(f"/api/reports/{first_id}").content == first[0]
    print(f"first report unchanged: {unchanged}")
    meta = second[1].meta
    return (
        unchanged
        and meta.analysis_date.isoformat() == body["analysis_date"] <= analysis_date
        and meta.changed_from_date == first[1].meta.analysis_date
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="base address of a running service")
    parser.add_argument("values", nargs="*", help="parcel identifier, crop, analysis date")
    arguments = parser.parse_args()
    values = (*arguments.values, *DEFAULTS[len(arguments.values):])[:3]
    with api_client(arguments.url) as client:
        ok = run(client, *values)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
