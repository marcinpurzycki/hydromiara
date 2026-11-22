"""Weather adapter on recorded answers of the weather archive."""

import asyncio
import copy
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.sources import weather_params as params
from app.sources.weather import (
    WeatherSource,
    WeatherSourceError,
    find_limitations,
    parse_response,
    series_start,
)

FIXTURES = Path(__file__).parent / "fixtures" / "open_meteo"
VARIABLES = params.DAILY_VARIABLES
LAT, LON = 52.75, 18.25


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def without_values(payload: dict, positions: list[int]) -> dict:
    """The recorded answer with the values of the given days replaced by nulls."""
    changed = copy.deepcopy(payload)
    for name in VARIABLES:
        for position in positions:
            changed["daily"][name][position] = None
    return changed


def source_answering(payload: dict, status: int = 200, seen: list | None = None) -> WeatherSource:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return WeatherSource(transport=httpx.MockTransport(handler))


def test_series_starts_before_the_multiyear_window():
    start = series_start(date(2019, 6, 15))
    assert start < date(2009, 1, 1)
    assert (date(2009, 1, 1) - start).days == params.BALANCE_WARMUP_DAYS


def test_historical_answer_is_normalised():
    data = parse_response(recorded("archive_historical.json"), date(2019, 6, 15))
    assert (data.grid_lat, data.grid_lon) == (52.759224, 18.202248)
    assert [day.date for day in data.days] == [date(2019, 6, d) for d in range(1, 16)]
    first, wet = data.days[0], data.days[12]
    # The mean temperature is not requested; its field stays empty.
    assert (first.precipitation_mm, first.et0_mm, first.temperature_mean_c) == (0.2, 3.66, None)
    assert wet.precipitation_mm == 10.8
    assert find_limitations(data, date(2019, 6, 1), date(2019, 6, 15)) == []


def test_days_after_the_analysis_date_are_dropped():
    data = parse_response(recorded("archive_historical.json"), date(2019, 6, 10))
    assert data.days[-1].date == date(2019, 6, 10)
    assert len(data.days) == 10


def test_recent_answer_reaches_the_analysis_date():
    data = parse_response(recorded("archive_recent.json"), date(2026, 11, 21))
    assert data.days[-1].date == date(2026, 11, 21)
    assert find_limitations(data, date(2026, 11, 1), date(2026, 11, 21)) == []


def test_series_ending_early_is_reported_as_limitation():
    payload = without_values(recorded("archive_recent.json"), [-5, -4, -3, -2, -1])
    data = parse_response(payload, date(2026, 11, 21))
    assert data.days[-1].date == date(2026, 11, 16)
    (gap,) = find_limitations(data, date(2026, 11, 1), date(2026, 11, 21))
    assert gap.affects == "current"
    assert gap.permanent is False
    assert "16.11.2026" in gap.text
    assert "5 dni przed Datą analizy (21.11.2026)" in gap.text


def test_one_missing_day_is_worded_in_singular():
    payload = without_values(recorded("archive_recent.json"), [-1])
    data = parse_response(payload, date(2026, 11, 21))
    (gap,) = find_limitations(data, date(2026, 11, 1), date(2026, 11, 21))
    assert "1 dzień przed Datą analizy" in gap.text


def test_missing_days_inside_the_series_are_reported():
    payload = without_values(recorded("archive_historical.json"), [3, 4])
    data = parse_response(payload, date(2019, 6, 15))
    assert len(data.days) == 15
    assert data.days[3].precipitation_mm is None
    (gap,) = find_limitations(data, date(2019, 6, 1), date(2019, 6, 15))
    assert gap.affects == "all"
    assert "dla 2 dni" in gap.text


def test_series_starting_late_is_reported_for_the_multiyear_verdict():
    data = parse_response(recorded("archive_historical.json"), date(2019, 6, 15))
    (gap,) = find_limitations(data, date(2019, 5, 1), date(2019, 6, 15))
    assert gap.affects == "multiyear"
    assert "01.06.2019" in gap.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"latitude": 52.7, "longitude": 18.2, "daily": {"time": ["2019-06-01"]}},
        {
            "latitude": 52.7,
            "longitude": 18.2,
            "daily": {
                "time": ["2019-06-01", "2019-06-02"],
                "precipitation_sum": [0.0],
                "et0_fao_evapotranspiration": [1.0, 2.0],
            },
        },
        {
            "latitude": 52.7,
            "longitude": 18.2,
            "daily": {
                "time": ["2019-06-01"],
                "precipitation_sum": [None],
                "et0_fao_evapotranspiration": [None],
            },
        },
    ],
)
def test_unreadable_answer_is_an_error(payload):
    with pytest.raises(WeatherSourceError):
        parse_response(payload, date(2019, 6, 15))


def test_request_carries_only_point_and_date_range():
    seen: list[httpx.Request] = []
    source = source_answering(recorded("archive_historical.json"), seen=seen)
    result = asyncio.run(source.fetch(LAT, LON, date(2019, 6, 15)))

    (request,) = seen
    assert str(request.url).startswith(params.ARCHIVE_URL)
    assert dict(request.url.params) == {
        "latitude": "52.75000",
        "longitude": "18.25000",
        "start_date": series_start(date(2019, 6, 15)).isoformat(),
        "end_date": "2019-06-15",
        "daily": "precipitation_sum,et0_fao_evapotranspiration",
        "timezone": "Europe/Warsaw",
    }
    assert request.headers["user-agent"] == params.USER_AGENT
    assert result.data is not None


def test_fetch_describes_how_the_series_was_obtained():
    source = source_answering(recorded("archive_historical.json"))
    data, outcome, limitations = asyncio.run(source.fetch(LAT, LON, date(2019, 6, 15)))

    assert data is not None and data.days[-1].date == date(2019, 6, 15)
    assert outcome.topic == "weather"
    assert outcome.ok and outcome.chain_step == 1
    assert outcome.source_name == params.SOURCE_NAME
    assert outcome.data_date == "2019-06-01/2019-06-15"
    # The recorded answer covers two weeks, so the start of the window is missing.
    assert [limitation.affects for limitation in limitations] == ["multiyear"]
    assert outcome.message == limitations[0].text


def test_fetch_reports_the_gap_before_the_analysis_date():
    payload = without_values(recorded("archive_recent.json"), [-3, -2, -1])
    source = source_answering(payload)
    data, outcome, limitations = asyncio.run(source.fetch(LAT, LON, date(2026, 11, 21)))

    assert data is not None and data.days[-1].date == date(2026, 11, 18)
    assert outcome.ok
    assert outcome.data_date.endswith("/2026-11-18")
    assert "current" in [limitation.affects for limitation in limitations]


def test_fetch_survives_a_refused_request():
    source = source_answering(recorded("error_end_date.json"), status=400)
    data, outcome, limitations = asyncio.run(source.fetch(LAT, LON, date(2027, 1, 1)))

    assert data is None and limitations == []
    assert not outcome.ok
    assert outcome.chain_step is None and outcome.source_name is None
    assert outcome.data_date is None
    assert outcome.message


def test_fetch_survives_a_timeout_and_a_non_json_answer():
    def timing_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    def not_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    for handler in (timing_out, not_json):
        source = WeatherSource(transport=httpx.MockTransport(handler))
        data, outcome, _ = asyncio.run(source.fetch(LAT, LON, date(2019, 6, 15)))
        assert data is None
        assert not outcome.ok
