"""Smoke check of whole analyses with every connected source, live (needs network).

Run from the backend directory:
    EDO_DATA_PATH=/path/to/drought/files python -m tests.smoke.full_analysis_smoke
    python -m tests.smoke.full_analysis_smoke --runs 3 --date 2023-06-20 --date today
    python -m tests.smoke.full_analysis_smoke --url http://127.0.0.1:8000

Runs one analysis after another for three parcels in different regions, for
each analysis date and `--runs` times, and prints a table: total time, time
and result of every source, confidence of both verdicts, stored sizes.
Without --url the application runs in this process with a temporary report
database and the source times come from the stored source data; with --url
they are not available (they are in the log of the service).

Analyses start at least `--spacing` seconds apart, because the soil service
allows five calls per minute. Exits with 1 when an analysis fails or takes
longer than the time budget; a source without data is a normal result.
"""

import argparse
import contextlib
import os
import sys
import tempfile
import time
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from app.contracts.report import Report
from app.orchestrator.params import ANALYSIS_BUDGET_S
from app.storage.params import DB_PATH_ENV
from app.storage.reports import ReportStore

PARCELS = ("040704_2.0020.34/2", "141201_1.0001.6509", "060405_2.0223.756")
CROP = "winter_wheat"
DATES = ("2023-06-20", "today")
TOPICS = ("parcel", "weather", "soil", "terrain", "satellite", "drought_background")


@contextlib.contextmanager
def api_client(url: str | None):
    """The client and, when the application runs here, its report store."""
    if url:
        with httpx.Client(base_url=url, timeout=30.0) as client:
            yield client, None
        return
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reports.sqlite3"
        os.environ[DB_PATH_ENV] = str(path)
        from app.main import app

        with TestClient(app) as client:
            yield client, ReportStore(path)


def analyse(client, store: ReportStore | None, parcel_id: str, analysis_date: str) -> dict:
    """One analysis from start to Report; what happened, as a row of the table."""
    request = {"parcel_id": parcel_id, "crop_id": CROP, "analysis_date": analysis_date}
    started = time.monotonic()
    response = client.post("/api/analyses", json=request)
    if response.status_code != 202:
        return {"ok": False, "why": f"not accepted: {response.status_code} {response.text}"}
    report_id = response.json()["report_id"]
    while True:
        status = client.get(f"/api/analyses/{report_id}/status").json()
        if status["state"] != "running" or time.monotonic() - started > 2 * ANALYSIS_BUDGET_S:
            break
        time.sleep(0.1)
    row = {"total_s": time.monotonic() - started, "state": status["state"], "sources": {}}
    for source in status["sources"]:
        if source["state"] == "missing":
            print(f"    {source['id']}: {source['note']}")
    answer = client.get(f"/api/reports/{report_id}")
    if answer.status_code != 200:
        return {**row, "ok": False, "why": f"no report: {answer.status_code} {answer.text}"}
    report = Report.model_validate(answer.json())
    durations = {}
    if store is not None:
        stored = store.inputs(report_id, datetime.now(UTC)).source_data
        durations = {outcome.topic: outcome.duration_s for outcome in stored.outcomes}
        row["source_data_bytes"] = len(stored.model_dump_json().encode())
    for source in report.sources:
        row["sources"][source.topic] = (not source.missing, durations.get(source.topic))
    capacity = next(e.values for e in report.trace if e.rule_id == "root_zone.capacity")
    row.update(
        ok=status["state"] == "done" and row["total_s"] <= ANALYSIS_BUDGET_S,
        why=f"state {status['state']}, {row['total_s']:.1f} s",
        capacity=f"{capacity['capacity_source']} {capacity['total_available_water_mm']} mm",
        current=f"{report.current_status.label} / {report.current_status.confidence.level}",
        multiyear=(
            f"{report.multiyear_susceptibility.deficit_years}"
            f"/{report.multiyear_susceptibility.total_years}"
            f" / {report.multiyear_susceptibility.confidence.level}"
        ),
        report_bytes=len(answer.content),
    )
    return row


def cell(result: tuple[bool, float | None] | None) -> str:
    if result is None:
        return "-"
    arrived, duration = result
    mark = "ok" if arrived else "MISSING"
    return mark if duration is None else f"{mark} {duration:.1f}"


def print_row(label: str, row: dict) -> None:
    if "capacity" not in row:
        print(f"{label} FAILED: {row['why']}")
        return
    sources = " | ".join(f"{cell(row['sources'].get(topic)):<12}" for topic in TOPICS)
    sizes = f"{row.get('source_data_bytes', 0) // 1000}+{row['report_bytes'] // 1000} kB"
    print(
        f"{label} | {row['total_s']:5.1f} s | {sources} | {row['capacity']:<28} | "
        f"{row['current']:<26} | {row['multiyear']:<14} | {sizes}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="base address of a running service")
    parser.add_argument("--runs", type=int, default=2, help="repeats of every analysis")
    parser.add_argument("--date", action="append", help="analysis date or 'today'; repeatable")
    parser.add_argument("--parcel", action="append", help="parcel identifier; repeatable")
    parser.add_argument("--spacing", type=float, default=13.0, help="seconds between starts")
    arguments = parser.parse_args()
    dates = [
        date.today().isoformat() if value == "today" else value
        for value in (arguments.date or DATES)
    ]
    rows = []
    with api_client(arguments.url) as (client, store):
        last_start = None
        for run in range(1, arguments.runs + 1):
            for parcel_id in arguments.parcel or PARCELS:
                for analysis_date in dates:
                    if last_start is not None:
                        time.sleep(max(0.0, arguments.spacing - (time.monotonic() - last_start)))
                    last_start = time.monotonic()
                    label = f"{run} {parcel_id:<20} {analysis_date}"
                    print(f"running {label}")
                    rows.append((label, analyse(client, store, parcel_id, analysis_date)))
    print("\nrun parcel date | total | " + " | ".join(TOPICS)
          + " | water capacity | current / confidence | multi-year / confidence | stored")
    for label, row in rows:
        print_row(label, row)
    done = [row for _, row in rows if "capacity" in row]
    if done:
        totals = sorted(row["total_s"] for row in done)
        print(f"\ntotal time: min {totals[0]:.1f} s, median {totals[len(totals) // 2]:.1f} s, "
              f"max {totals[-1]:.1f} s over {len(done)} analyses")
        for topic in TOPICS[2:]:
            arrived = sum(1 for row in done if row["sources"].get(topic, (False,))[0])
            print(f"{topic}: data in {arrived} of {len(done)} analyses")
    failed = [label for label, row in rows if not row["ok"]]
    print("OK" if not failed else f"FAILED: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
