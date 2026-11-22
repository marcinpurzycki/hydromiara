"""Last day of the weather series: the analysis date, but never the current day.

The clock is given to the adapter, so every case names its own "now". The
recorded answer `archive_recent.json` holds the days 1-21.11.2026.
"""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.orchestrator import params as run_params
from app.sources import weather_params as params
from app.sources.weather import WeatherSource, series_end, series_start

FIXTURES = Path(__file__).parent / "fixtures" / "open_meteo"
LAT, LON = 52.75, 18.25
# 22.11.2026, 11:00 in Poland.
NOON = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)


def recorded(name: str = "archive_recent.json") -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fetch(analysis_date: date, now: datetime, payload: dict | None = None):
    """The result of one fetch and the requests the archive saw."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload or recorded())

    source = WeatherSource(transport=httpx.MockTransport(handler), clock=lambda: now)
    return asyncio.run(source.fetch(LAT, LON, analysis_date)), seen


@pytest.mark.parametrize(
    ("analysis_date", "expected"),
    [
        (date(2026, 11, 22), date(2026, 11, 21)),  # today: ends yesterday
        (date(2026, 11, 21), date(2026, 11, 21)),  # yesterday: a finished day
        (date(2026, 11, 15), date(2026, 11, 15)),  # a week ago
        (date(2019, 6, 15), date(2019, 6, 15)),  # historical
        (date(2026, 11, 30), date(2026, 11, 21)),  # a later date never reaches the archive
    ],
)
def test_last_day_for_analysis_dates_seen_from_one_moment(analysis_date, expected):
    assert series_end(analysis_date, NOON) == expected


@pytest.mark.parametrize(
    ("now", "today_in_poland"),
    [
        # Winter: Poland is one hour ahead of UTC.
        (datetime(2026, 11, 21, 22, 59, tzinfo=UTC), date(2026, 11, 21)),
        (datetime(2026, 11, 21, 23, 0, tzinfo=UTC), date(2026, 11, 22)),
        (datetime(2026, 11, 22, 0, 0, tzinfo=UTC), date(2026, 11, 22)),
        # Summer: two hours ahead.
        (datetime(2026, 7, 14, 21, 59, tzinfo=UTC), date(2026, 7, 14)),
        (datetime(2026, 7, 14, 22, 0, tzinfo=UTC), date(2026, 7, 15)),
        # The nights of the clock change (29.03.2026 and 25.10.2026).
        (datetime(2026, 3, 28, 23, 30, tzinfo=UTC), date(2026, 3, 29)),
        (datetime(2026, 3, 29, 21, 59, tzinfo=UTC), date(2026, 3, 29)),
        (datetime(2026, 3, 29, 22, 0, tzinfo=UTC), date(2026, 3, 30)),
        (datetime(2026, 10, 24, 22, 30, tzinfo=UTC), date(2026, 10, 25)),
        (datetime(2026, 10, 25, 22, 59, tzinfo=UTC), date(2026, 10, 25)),
        (datetime(2026, 10, 25, 23, 0, tzinfo=UTC), date(2026, 10, 26)),
    ],
)
def test_today_is_counted_in_polish_time(now, today_in_poland):
    yesterday = today_in_poland - timedelta(days=1)
    assert series_end(today_in_poland, now) == yesterday
    assert series_end(yesterday, now) == yesterday


def test_last_day_is_never_today_and_never_after_the_utc_day():
    moment = datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
    for _ in range(24 * 4 * 4):  # every quarter of an hour over the clock change
        end = series_end(date(2030, 1, 1), moment)
        assert end <= moment.date()
        assert (moment.date() - end).days <= 1
        moment += timedelta(minutes=15)


def test_request_for_today_ends_yesterday_and_names_no_model():
    result, (request,) = fetch(date(2026, 11, 22), NOON)
    query = dict(request.url.params)
    assert query == {
        "latitude": "52.75000",
        "longitude": "18.25000",
        "start_date": series_start(date(2026, 11, 22)).isoformat(),
        "end_date": "2026-11-21",
        "daily": "precipitation_sum,et0_fao_evapotranspiration",
        "timezone": "Europe/Warsaw",
    }
    assert "models" not in query
    assert params.DAILY_VARIABLES == ("precipitation_sum", "et0_fao_evapotranspiration")
    assert result.data.days[-1].date == date(2026, 11, 21)
    assert all(day.temperature_mean_c is None for day in result.data.days)


def test_request_just_after_polish_midnight_is_accepted_by_the_archive():
    # 00:30 in Poland on 22.11 is still 21.11 in UTC, the last day the archive takes.
    now = datetime(2026, 11, 21, 23, 30, tzinfo=UTC)
    _, (request,) = fetch(date(2026, 11, 22), now)
    assert request.url.params["end_date"] == "2026-11-21"
    assert date.fromisoformat(request.url.params["end_date"]) <= now.date()


def test_series_for_today_is_described_without_lowering_the_confidence():
    result, _ = fetch(date(2026, 11, 22), NOON)
    current = [item for item in result.limitations if item.affects == "current"]
    assert [item.permanent for item in current] == [True]
    assert current[0].text == (
        "Dane pogodowe kończą się wczoraj (21.11.2026). Dzisiejszy dzień nie jest "
        "uwzględniony, bo jeszcze trwa."
    )
    assert current[0].text in result.outcome.message
    assert result.outcome.data_date.endswith("/2026-11-21")
    # The clock reading that chose the last day is the stored time of the fetch.
    assert result.outcome.fetched_at == NOON


def test_real_gap_before_today_is_still_a_limitation():
    payload = recorded()
    for name in params.DAILY_VARIABLES:
        payload["daily"][name][-1] = None
    result, _ = fetch(date(2026, 11, 22), NOON, payload)
    (gap,) = [item for item in result.limitations if item.affects == "current"]
    assert gap.permanent is False
    assert "20.11.2026, czyli 2 dni przed Datą analizy (22.11.2026)" in gap.text


def test_day_missing_before_a_past_analysis_date_is_a_limitation():
    payload = recorded()
    for name in params.DAILY_VARIABLES:
        payload["daily"][name][-1] = None
    result, (request,) = fetch(date(2026, 11, 21), NOON, payload)
    assert request.url.params["end_date"] == "2026-11-21"
    (gap,) = [item for item in result.limitations if item.affects == "current"]
    assert gap.permanent is False and "1 dzień przed Datą analizy" in gap.text


def test_days_the_archive_adds_after_the_last_day_are_not_kept():
    # The recorded answer reaches 21.11; seen from 20.11 it holds two days too many.
    now = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    result, (request,) = fetch(date(2026, 11, 20), now)
    assert request.url.params["end_date"] == "2026-11-19"
    assert max(day.date for day in result.data.days) == date(2026, 11, 19)


def test_adapter_waits_no_longer_than_the_analysis_gives_it():
    assert params.FETCH_BUDGET_S <= run_params.WEATHER_TIMEOUT_S
    assert params.TIMEZONE == run_params.LOCAL_TIMEZONE
