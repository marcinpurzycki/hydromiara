"""Scene search on a recorded answer of the scene catalogue, no network."""

import asyncio
import copy
import dataclasses
import json
from datetime import date

import httpx
import pytest

from app.sources import satellite_params as params
from app.sources.satellite_providers import EARTH_SEARCH
from app.sources.satellite_search import (
    SatelliteSearchError,
    SearchWindow,
    find_scenes,
    parse_items,
    search_body,
    search_windows,
)
from tests.satellite_helpers import OUTLINE, recorded_answer

JUNE = SearchWindow(start=date(2023, 6, 5), end=date(2023, 6, 20), anchor=date(2023, 6, 20))
GEOMETRY = OUTLINE.model_dump()


def search(transport: httpx.MockTransport, window: SearchWindow = JUNE, provider=EARTH_SEARCH):
    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await find_scenes(client, provider, GEOMETRY, window)

    return asyncio.run(run())


def spans(analysis_date: date) -> list[tuple[date, date]]:
    return [(window.start, window.end) for window in search_windows(analysis_date)]


def test_current_window_is_30_days_before_the_analysis_date_and_the_date_itself():
    current = search_windows(date(2023, 6, 20))[0]
    assert (current.start, current.end) == (date(2023, 5, 21), date(2023, 6, 20))
    assert current.current and current.anchor == date(2023, 6, 20)
    assert params.CURRENT_WINDOW_DAYS == 30


def test_earlier_years_get_15_days_on_each_side_of_the_same_day_for_5_years():
    windows = search_windows(date(2023, 6, 20))[1:]
    assert [(w.start, w.end) for w in windows] == [
        (date(year, 6, 5), date(year, 7, 5)) for year in (2022, 2021, 2020, 2019, 2018)
    ]
    assert not any(window.current for window in windows)
    assert (params.HISTORY_YEARS, params.HISTORY_HALF_WINDOW_DAYS) == (5, 15)


@pytest.mark.parametrize(
    "analysis_date",
    [date(2023, 6, 20), date(2024, 2, 29), date(2024, 1, 5), date(2023, 12, 31), date(2016, 3, 1)],
)
def test_no_window_reaches_past_the_analysis_date(analysis_date):
    windows = search_windows(analysis_date)
    assert len(windows) == 1 + params.HISTORY_YEARS
    assert max(window.end for window in windows) == analysis_date
    assert all(window.end < windows[0].start for window in windows[1:])


def test_leap_day_falls_back_to_28_february_in_other_years():
    windows = search_windows(date(2024, 2, 29))
    assert spans(date(2024, 2, 29))[0] == (date(2024, 1, 30), date(2024, 2, 29))
    assert [window.anchor for window in windows[1:]] == [
        date(2023, 2, 28), date(2022, 2, 28), date(2021, 2, 28), date(2020, 2, 29), date(2019, 2, 28)
    ]  # fmt: skip
    assert spans(date(2024, 2, 29))[1] == (date(2023, 2, 13), date(2023, 3, 15))
    assert spans(date(2024, 2, 29))[4] == (date(2020, 2, 14), date(2020, 3, 15))


def test_windows_around_the_turn_of_the_year_cross_it():
    assert spans(date(2024, 1, 5))[:2] == [
        (date(2023, 12, 6), date(2024, 1, 5)),
        (date(2022, 12, 21), date(2023, 1, 20)),
    ]


def test_request_carries_only_the_outline_the_dates_and_the_collection():
    body = search_body(EARTH_SEARCH, GEOMETRY, JUNE)
    assert body["collections"] == ["sentinel-2-l2a"]
    assert body["intersects"] == GEOMETRY
    assert body["datetime"] == "2023-06-05T00:00:00Z/2023-06-20T23:59:59Z"
    assert set(body) == {"collections", "intersects", "datetime", "limit", "fields"}


def test_request_asks_only_for_what_reading_needs():
    body = search_body(EARTH_SEARCH, GEOMETRY, JUNE)
    assert body["limit"] == 2000
    wanted = body["fields"]["include"]
    assert {"id", "properties.datetime", "properties.s2:processing_baseline"} <= set(wanted)
    assert "properties.grid:code" in wanted and "assets.nir08.href" in wanted
    assert {"links", "geometry", "bbox", "stac_extensions"} <= set(body["fields"]["exclude"])
    assert "assets.nir08" not in body["fields"]["exclude"]
    assert "eo:cloud_cover" not in str(body)  # no filter on the cloud cover of the whole scene


def test_recorded_answer_is_reduced_to_days_and_file_addresses():
    items = parse_items(recorded_answer(), JUNE, EARTH_SEARCH)
    assert len(items) == 12
    assert {item.date for item in items} == {date(2023, 6, d) for d in (6, 9, 11, 14, 16, 19)}
    assert all(set(item.hrefs) == set(params.REQUIRED_ASSETS) for item in items)
    assert items[0].hrefs["scl"].endswith("/SCL.tif")
    assert items[0].hrefs["red"].endswith("/B04.tif")
    assert items[0].hrefs["nir08"].endswith("/B8A.tif")
    assert {item.tile for item in items} == {"MGRS-34UCD", "MGRS-33UYU"}
    assert {item.baseline for item in items} == {"05.09"}


def test_scenes_outside_the_window_are_dropped():
    window = SearchWindow(date(2023, 6, 5), date(2023, 6, 12), date(2023, 6, 12))
    items = parse_items(recorded_answer(), window, EARTH_SEARCH)
    assert {item.date for item in items} == {date(2023, 6, d) for d in (6, 9, 11)}


def test_scene_without_a_needed_file_is_skipped():
    payload = recorded_answer()
    del payload["features"][0]["assets"]["swir16"]
    assert len(parse_items(payload, JUNE, EARTH_SEARCH)) == 11


def test_unreadable_answer_is_an_error():
    with pytest.raises(SatelliteSearchError):
        parse_items({"type": "FeatureCollection"}, JUNE, EARTH_SEARCH)
    with pytest.raises(SatelliteSearchError):
        parse_items(
            {"features": [{"id": "x", "properties": {"datetime": "yesterday"}}]}, JUNE, EARTH_SEARCH
        )


def test_search_stops_on_a_page_that_is_not_full():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=recorded_answer())

    items = search(httpx.MockTransport(handler))
    assert len(items) == 12
    assert len(seen) == 1  # the answer links a next page although there is none
    assert seen[0].method == "POST" and str(seen[0].url) == EARTH_SEARCH.search_url


def test_search_follows_the_next_link_when_the_page_is_full():
    first = recorded_answer()
    second = copy.deepcopy(first)
    first["features"], second["features"] = first["features"][:8], second["features"][8:12]
    small_pages = dataclasses.replace(EARTH_SEARCH, page_limit=8)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=second if "next" in bodies[-1] else first)

    items = search(httpx.MockTransport(handler), provider=small_pages)
    assert len(bodies) == 2
    assert bodies[1] == first["links"][0]["body"]  # the link body replaces the request body
    assert len(items) == 12


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(503, text="unavailable"),
        lambda request: httpx.Response(200, text="<html>"),
        lambda request: httpx.Response(200, json=[1, 2]),
    ],
)
def test_failed_search_is_an_error(handler):
    with pytest.raises(SatelliteSearchError):
        search(httpx.MockTransport(handler))


def test_connection_failure_is_an_error():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(SatelliteSearchError):
        search(httpx.MockTransport(handler))
