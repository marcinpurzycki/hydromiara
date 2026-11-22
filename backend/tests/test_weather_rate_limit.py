"""The weather archive refusing a request for the rate limit (429)."""

import asyncio
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from app.sources import weather_params as params
from app.sources.weather import WeatherSource
from tests.analysis_helpers import assert_error, start, status_of, wait_finished

FIXTURES = Path(__file__).parent / "fixtures" / "open_meteo"
RECORDED = json.loads((FIXTURES / "archive_historical.json").read_text(encoding="utf-8"))
LAT, LON = 52.74927, 18.20085
DAY = date(2019, 6, 15)
NOW = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)
REFUSAL = {
    "error": True,
    "reason": "Hourly API request limit exceeded. Please try again in the next hour.",
}
ALLOWANCE = {
    "X-RateLimit-Cost": "58.54286",
    "X-RateLimit-Remaining": "541.45715",
    "X-RateLimit-Window": "60",
}


def refused(retry_after: str | None) -> httpx.Response:
    headers = {"X-RateLimit-Remaining": "0.0", "X-RateLimit-Window": "3600"}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return httpx.Response(429, json=REFUSAL, headers=headers)


def run(answers: list[httpx.Response], budget_s: float = params.FETCH_BUDGET_S):
    """One fetch against the given answers; the result, the request count, the waits."""
    left = list(answers)
    seen: list[httpx.Request] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return left.pop(0)

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    source = WeatherSource(
        transport=httpx.MockTransport(handler), clock=lambda: NOW, sleep=sleep, budget_s=budget_s
    )
    return asyncio.run(source.fetch(LAT, LON, DAY)), len(seen), waits


def answered() -> httpx.Response:
    return httpx.Response(200, json=RECORDED, headers=ALLOWANCE)


def test_short_wait_is_kept_and_the_request_repeated_once():
    result, requests, waits = run([refused("2"), answered()])
    assert (requests, waits) == (2, [2.0])
    assert result.data is not None and result.outcome.ok


def test_long_wait_ends_the_fetch_at_once_with_its_own_message():
    result, requests, waits = run([refused("96"), answered()])
    assert (requests, waits) == (1, [])
    assert result.data is None and not result.outcome.ok
    assert result.outcome.message == (
        "Serwis pogodowy chwilowo odmówił odpowiedzi z powodu limitu zapytań. Bez danych "
        "pogodowych nie można ocenić sytuacji wodnej. Spróbuj ponownie za kilka minut."
    )
    assert result.limitations == []


def test_wait_has_to_leave_time_for_the_repeated_request():
    fits = params.FETCH_BUDGET_S - params.RETRY_REQUEST_RESERVE_S - 1
    _, requests, waits = run([refused(str(fits)), answered()])
    assert (requests, waits) == (2, [fits])
    # The same wait does not fit when the analysis gives the source less time.
    _, requests, waits = run([refused(str(fits)), answered()], budget_s=fits)
    assert (requests, waits) == (1, [])


def test_refusal_that_names_no_wait_is_not_repeated():
    for value in (None, "soon", "-1"):
        result, requests, waits = run([refused(value), answered()])
        assert (requests, waits) == (1, [])
        assert "limitu zapytań" in result.outcome.message


def test_second_refusal_is_final():
    result, requests, waits = run([refused("1"), refused("1"), answered()])
    assert (requests, waits) == (2, [1.0])
    assert result.data is None and "limitu zapytań" in result.outcome.message


def test_other_failures_keep_the_general_message():
    result, requests, _ = run([httpx.Response(400, json={"error": True, "reason": "range"})])
    assert requests == 1 and result.data is None
    assert result.outcome.message == params.FAILURE_MESSAGES[params.REASON_NO_ANSWER]
    assert "limitu" not in result.outcome.message


def test_allowance_headers_go_to_the_log_without_the_request(caplog):
    with caplog.at_level(logging.INFO, logger="hydromiara.sources.weather"):
        run([answered()])
    (line,) = [record.getMessage() for record in caplog.records]
    assert "status=200" in line
    assert "X-RateLimit-Cost=58.54286" in line
    assert "X-RateLimit-Remaining=541.45715" in line
    assert "X-RateLimit-Window=60" in line
    assert "Retry-After=-" in line
    # Nothing that says where the parcel is or which day was asked for.
    for private in ("52.7", "18.2", "latitude", "2019", "http"):
        assert private not in line


def test_refusal_is_logged_with_the_wait_and_the_reason_code(caplog):
    with caplog.at_level(logging.INFO, logger="hydromiara.sources.weather"):
        run([refused("96")])
    first, second = [record.getMessage() for record in caplog.records]
    assert "status=429" in first and "Retry-After=96" in first
    assert "X-RateLimit-Window=3600" in first
    assert second.endswith(f"reason={params.REASON_RATE_LIMITED}")


def test_analysis_refused_by_the_archive_ends_with_the_message_about_the_limit(client, weather):
    weather.status_code = 429
    weather.payload = json.dumps(REFUSAL)
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "failed"
    assert len(weather.requests) == 1
    (note,) = [s["note"] for s in status_of(client, report_id)["sources"] if s["id"] == "weather"]
    assert note == params.FAILURE_MESSAGES[params.REASON_RATE_LIMITED]
    response = client.get(f"/api/reports/{report_id}")
    assert_error(response, 404, "weather_unavailable")
    assert response.json()["message"].endswith(note)
