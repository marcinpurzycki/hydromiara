"""Scene search on a recorded answer of the scene catalogue, no network."""

import asyncio
import copy
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
    group_by_day,
    parse_items,
    search_body,
    search_windows,
)
from tests.satellite_helpers import OUTLINE, recorded_answer

JUNE = SearchWindow(start=date(2023, 6, 5), end=date(2023, 6, 20))
GEOMETRY = OUTLINE.model_dump()


def search(transport: httpx.MockTransport, window: SearchWindow = JUNE):
    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await find_scenes(client, EARTH_SEARCH, GEOMETRY, window)

    return asyncio.run(run())


def test_windows_end_on_the_analysis_date_and_the_same_day_of_earlier_years():
    windows = search_windows(date(2023, 6, 20))
    ends = [window.end for window in windows]
    assert ends == [date(year, 6, 20) for year in (2023, 2022, 2021, 2020)]
    assert len(windows) == params.PREVIOUS_YEARS + 1
    assert all((window.end - window.start).days == params.WINDOW_DAYS for window in windows)
    assert all(window.end <= date(2023, 6, 20) for window in windows)


def test_leap_day_falls_back_to_28_february_in_other_years():
    ends = [window.end for window in search_windows(date(2024, 2, 29))]
    assert ends == [date(2024, 2, 29), date(2023, 2, 28), date(2022, 2, 28), date(2021, 2, 28)]


def test_request_carries_only_the_outline_the_dates_and_the_collection():
    body = search_body(EARTH_SEARCH, GEOMETRY, JUNE)
    assert body["collections"] == ["sentinel-2-l2a"]
    assert body["intersects"] == GEOMETRY
    assert body["datetime"] == "2023-06-05T00:00:00Z/2023-06-20T23:59:59Z"
    assert set(body) == {"collections", "intersects", "datetime", "limit", "fields"}


def test_recorded_answer_is_reduced_to_days_and_file_addresses():
    items = parse_items(recorded_answer(), JUNE, EARTH_SEARCH)
    assert len(items) == 12
    assert {item.date for item in items} == {date(2023, 6, d) for d in (6, 9, 11, 14, 16, 19)}
    assert all(set(item.hrefs) == set(params.REQUIRED_ASSETS) for item in items)
    assert items[0].hrefs["scl"].endswith("/SCL.tif")
    assert items[0].hrefs["red"].endswith("/B04.tif")


def test_copies_of_one_day_are_grouped_newest_day_first():
    items = parse_items(recorded_answer(), JUNE, EARTH_SEARCH)
    days = group_by_day(items + items[:3])  # the same scene listed twice is one copy
    assert [copies[0].date for copies in days] == [
        date(2023, 6, d) for d in (19, 16, 14, 11, 9, 6)
    ]
    assert all(len(copies) == 2 for copies in days)
    assert [item.scene_id for item in days[0]] == [
        "S2A_34UCD_20230619_0_L2A",
        "S2A_33UYU_20230619_0_L2A",
    ]
    assert group_by_day(list(reversed(items))) == group_by_day(items)


def test_scenes_outside_the_window_are_dropped():
    window = SearchWindow(start=date(2023, 5, 13), end=date(2023, 6, 12))
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

    days = search(httpx.MockTransport(handler))
    assert len(days) == 6
    assert len(seen) == 1  # the answer links a next page although there is none
    assert seen[0].method == "POST" and str(seen[0].url) == EARTH_SEARCH.search_url


def test_search_follows_the_next_link_when_the_page_is_full(monkeypatch):
    first = recorded_answer()
    second = copy.deepcopy(first)
    first["features"], second["features"] = first["features"][:8], second["features"][8:]
    monkeypatch.setattr(params, "SEARCH_PAGE_LIMIT", 8)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=second if "next" in bodies[-1] else first)

    days = search(httpx.MockTransport(handler))
    assert len(bodies) == 2
    assert bodies[1] == first["links"][0]["body"]  # the link body replaces the request body
    assert sum(len(copies) for copies in days) == 12


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
