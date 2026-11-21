"""Smoke check of a whole analysis against the live sources (needs network).

Run from the backend directory:
    python -m tests.smoke.analysis_smoke [PARCEL_ID [CROP_ID [ANALYSIS_DATE]]]
    python -m tests.smoke.analysis_smoke --url http://127.0.0.1:8000 [...]

Without --url the application runs in this process with a temporary report
database; with --url the check goes through a running service. Starts one
analysis, follows its progress, reads the Report twice and prints the total
time and the time of every source. Exits with 1 when the analysis fails, takes
longer than the time budget or the two reads differ.
"""

import argparse
import contextlib
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx

from app.contracts.report import Report
from app.orchestrator.params import ANALYSIS_BUDGET_S
from app.storage.params import DB_PATH_ENV

DEFAULTS = ("040704_2.0020.34/2", "winter_wheat", "2023-06-20")


@contextlib.contextmanager
def api_client(url: str | None):
    if url:
        with httpx.Client(base_url=url, timeout=30.0) as client:
            yield client
        return
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as directory:
        os.environ[DB_PATH_ENV] = str(Path(directory) / "reports.sqlite3")
        from app.main import app

        with TestClient(app) as client:
            yield client


def run(client, parcel_id: str, crop_id: str, analysis_date: str) -> bool:
    request = {"parcel_id": parcel_id, "crop_id": crop_id, "analysis_date": analysis_date}
    started = time.monotonic()
    response = client.post("/api/analyses", json=request)
    accepted_s = time.monotonic() - started
    if response.status_code != 202:
        print(f"NOT ACCEPTED: {response.status_code} {response.text}")
        return False
    report_id = response.json()["report_id"]
    print(f"accepted in {accepted_s:.2f} s")

    while True:
        status = client.get(f"/api/analyses/{report_id}/status").json()
        if status["state"] != "running" or time.monotonic() - started > 2 * ANALYSIS_BUDGET_S:
            break
        time.sleep(0.1)
    total_s = time.monotonic() - started
    print(f"state {status['state']} after {total_s:.2f} s")
    for source in status["sources"]:
        print(f"  status {source['id']:<10} {source['state']:<8} {source['note'] or ''}")

    first = client.get(f"/api/reports/{report_id}")
    if first.status_code != 200:
        print(f"NO REPORT: {first.status_code} {first.text}")
        return False
    report = Report.model_validate(first.json())
    again = client.get(f"/api/reports/{report_id}")
    for source in report.sources:
        print(f"  source {source.topic:<10} missing={source.missing} data {source.data_date}")
    current, multiyear = report.current_status, report.multiyear_susceptibility
    print(f"headline: {report.headline}")
    print(f"current: level {current.deficit_level} ({current.label}); "
          f"multi-year: {multiyear.deficit_years}/{multiyear.total_years}")
    for limitation in report.limitations:
        print(f"  limitation ({limitation.affects}): {limitation.text}")
    print(f"report {len(first.content)} bytes, second read identical: "
          f"{again.content == first.content}")
    return (
        status["state"] == "done"
        and total_s <= ANALYSIS_BUDGET_S
        and again.content == first.content
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
