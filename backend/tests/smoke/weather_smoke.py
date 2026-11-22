"""Smoke check of the weather in whole analyses, live (needs network).

Run from the backend directory:
    python -m tests.smoke.weather_smoke
    python -m tests.smoke.weather_smoke --date today --parcel 040704_2.0020.34/2

Runs one whole analysis per date (by default today and a historical day) with
every connected source and prints: the last day of the weather series, what
the archive charged for the request (`X-RateLimit-Cost`) and how much of the
free allowance is left, the time of the weather request and of the analysis,
the confidence of both verdicts and the limitations of the Report.

The archive is asked once per analysis and never again after a refusal.
Exits with 1 when an analysis gives no Report, when the series ends after the
analysis date, or when a series for today does not end yesterday.
"""

import argparse
import os
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from app.contracts.report import Report
from app.orchestrator.params import ANALYSIS_BUDGET_S
from app.orchestrator.runtime import local_today
from app.orchestrator.sources import get_weather_source
from app.sources.weather import WeatherSource
from app.storage.params import DB_PATH_ENV
from app.storage.reports import ReportStore

PARCEL = "040704_2.0020.34/2"
CROP = "winter_wheat"
DATES = ("today", "2023-06-20")
HEADERS = ("X-RateLimit-Cost", "X-RateLimit-Remaining", "X-RateLimit-Window", "Retry-After")


class Watched(httpx.AsyncBaseTransport):
    """The real transport; keeps the status and the limit headers of every answer."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()
        self.answers: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        started = time.monotonic()
        response = await self._inner.handle_async_request(request)
        seen = {name: response.headers.get(name) for name in HEADERS}
        self.answers.append(
            {
                "status": response.status_code,
                "end_date": request.url.params.get("end_date"),
                "daily": request.url.params.get("daily"),
                "headers_s": round(time.monotonic() - started, 2),
                **seen,
            }
        )
        return response


def analyse(
    client, store: ReportStore, watched: Watched, parcel_id: str, analysis_date: date
) -> bool:
    request = {"parcel_id": parcel_id, "crop_id": CROP, "analysis_date": analysis_date.isoformat()}
    watched.answers.clear()
    started = time.monotonic()
    response = client.post("/api/analyses", json=request)
    if response.status_code != 202:
        print(f"  not accepted: {response.status_code} {response.text}")
        return False
    report_id = response.json()["report_id"]
    while True:
        status = client.get(f"/api/analyses/{report_id}/status").json()
        if status["state"] != "running" or time.monotonic() - started > 2 * ANALYSIS_BUDGET_S:
            break
        time.sleep(0.2)
    print(f"  analysis: {status['state']} in {time.monotonic() - started:.1f} s")
    for answer in watched.answers:
        print(f"  archive answer: {answer}")
    answer = client.get(f"/api/reports/{report_id}")
    if status["state"] != "done" or answer.status_code != 200:
        print(f"  NO REPORT: {answer.status_code} {answer.text[:400]}")
        return False
    report = Report.model_validate(answer.json())
    stored = store.inputs(report_id, datetime.now(UTC)).source_data
    outcome = next(item for item in stored.outcomes if item.topic == "weather")
    days = stored.weather.days
    last = days[-1].date
    print(f"  weather: {len(days)} days {days[0].date}..{last}, {outcome.duration_s:.2f} s")
    print(f"  weather note: {outcome.message}")
    print(f"  headline: {report.headline}")
    current, multiyear = report.current_status, report.multiyear_susceptibility
    print(f"  current: {current.label}, confidence {current.confidence.level}")
    print(
        f"  multi-year: {multiyear.deficit_years}/{multiyear.total_years}, "
        f"confidence {multiyear.confidence.level}"
    )
    for limitation in report.limitations:
        kind = "permanent" if limitation.permanent else "this analysis"
        print(f"  limitation ({limitation.affects}, {kind}): {limitation.text}")
    if analysis_date == local_today():
        return last == analysis_date - timedelta(days=1)
    return last <= analysis_date


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", action="append", help="analysis date or 'today'; repeatable")
    parser.add_argument("--parcel", default=PARCEL, help="parcel identifier")
    parser.add_argument("--spacing", type=float, default=13.0, help="seconds between starts")
    arguments = parser.parse_args()
    dates = [
        local_today() if value == "today" else date.fromisoformat(value)
        for value in (arguments.date or DATES)
    ]
    watched = Watched()
    results = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reports.sqlite3"
        os.environ[DB_PATH_ENV] = str(path)
        from fastapi.testclient import TestClient

        from app.main import app

        app.dependency_overrides[get_weather_source] = lambda: WeatherSource(transport=watched)
        with TestClient(app) as client:
            for position, analysis_date in enumerate(dates):
                if position:
                    time.sleep(arguments.spacing)
                print(f"analysis date {analysis_date}")
                store = ReportStore(path)
                results.append(analyse(client, store, watched, arguments.parcel, analysis_date))
    print("OK" if all(results) else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
