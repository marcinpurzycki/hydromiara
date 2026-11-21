"""Satellite adapter on a recorded catalogue answer and scene files built in the test."""

import asyncio
import json
import time
from contextlib import contextmanager
from datetime import date

import httpx
import pytest

from app.contracts.common import GeoJsonGeometry
from app.sources import satellite_params as params
from app.sources.satellite import SatelliteSource
from app.sources.satellite_limitations import TOO_SMALL_TEXT
from tests.satellite_helpers import OUTLINE, SceneFiles, catalogue, scene_id

ANALYSIS_DATE = date(2023, 6, 20)
DAYS = ("20230619", "20230616", "20230614", "20230611", "20230609", "20230606")


@pytest.fixture
def files(tmp_path) -> SceneFiles:
    return SceneFiles(tmp_path)


def fetch(files: SceneFiles, analysis_date: date = ANALYSIS_DATE, outline=OUTLINE, **kwargs):
    source = SatelliteSource(
        transport=kwargs.pop("transport", None) or catalogue(), opener=files.opener, **kwargs
    )
    return asyncio.run(source.fetch(outline, analysis_date))


def test_newest_clear_scene_is_read_with_its_indices(files):
    for day in DAYS:
        files.add(scene_id(day))
    data, outcome, limitations = fetch(files)
    assert [(s.date, s.clear_share_pct, s.ndvi, s.ndmi) for s in data.scenes] == [
        (date(2023, 6, 19), 100.0, 0.5, 0.2)
    ]
    assert (outcome.topic, outcome.ok, outcome.chain_step) == ("satellite", True, 1)
    assert outcome.source_name == params.SOURCE_NAME
    assert outcome.data_date == "2023-06-19/2023-06-19"
    # The recorded answer has no scenes for the three earlier years.
    assert [limitation.affects for limitation in limitations] == ["multiyear"] * 3
    assert "21.05.2022–20.06.2022" in outcome.message


def test_one_copy_of_a_day_is_read_and_older_days_are_left_alone(files):
    for day in DAYS:
        files.add(scene_id(day))
    fetch(files)
    newest = scene_id("20230619")
    assert files.opened_layers(newest) == {"scl", "red", "nir", "swir16"}
    assert len(files.opened) == len(set(files.opened))  # nothing is opened twice
    # The other copy of each day is never touched (the helper refuses unknown files),
    # and days beyond the first batch are not read once a clear scene is found.
    assert files.opened_layers(scene_id("20230609")) == set()
    assert files.opened_layers(scene_id("20230616")) <= {"scl"}


def test_scene_below_the_clear_share_is_skipped_without_reading_its_bands(files):
    files.add(scene_id("20230619"), scl=9)  # cloud over the whole parcel
    files.add(scene_id("20230616"), red=2000, nir=2000, swir=2000)
    files.add(scene_id("20230614"))
    data, _, _ = fetch(files)
    assert [(s.date, s.ndvi, s.ndmi) for s in data.scenes] == [(date(2023, 6, 16), 0.0, 0.0)]
    assert files.opened_layers(scene_id("20230619")) == {"scl"}


def test_no_scene_after_the_analysis_date_is_read(files):
    for day in DAYS:
        files.add(scene_id(day))
    seen = []
    data, _, _ = fetch(files, date(2023, 6, 12), transport=catalogue(seen=seen))
    assert [s.date for s in data.scenes] == [date(2023, 6, 11)]
    for later in ("20230619", "20230616", "20230614"):
        assert files.opened_layers(scene_id(later)) == set()
    ranges = [json.loads(request.content)["datetime"] for request in seen]
    assert len(ranges) == params.PREVIOUS_YEARS + 1
    assert max(searched.split("/")[1] for searched in ranges) == "2023-06-12T23:59:59Z"
    assert all(request.headers["user-agent"] == "hydro-analysis/0.1" for request in seen)


def test_copy_on_a_tile_that_misses_the_parcel_gives_way_to_the_other_copy(files):
    day = "20230619"
    files.add(scene_id(day), shift_m=5000.0)  # this tile lies beside the parcel
    files.add(scene_id(day, tile="33UYU"), red=500, nir=1500, swir=500)
    files.add(scene_id("20230616"))
    files.add(scene_id("20230614"))
    data, _, _ = fetch(files)
    assert [(s.date, s.ndvi, s.ndmi) for s in data.scenes] == [(date(2023, 6, 19), 0.5, 0.5)]
    assert files.opened_layers(scene_id(day)) == {"scl"}


def test_several_scenes_per_window_come_oldest_first_and_repeatably(files, monkeypatch):
    monkeypatch.setattr(params, "SCENES_PER_WINDOW", 3)
    for position, day in enumerate(DAYS):
        files.add(scene_id(day), scl=9 if day == "20230616" else 4, nir=3000 + 100 * position)
    first = fetch(files)
    second = fetch(files)
    assert [s.date for s in first.data.scenes] == [date(2023, 6, d) for d in (11, 14, 19)]
    assert first.data == second.data
    assert first.limitations == second.limitations
    assert first.outcome.data_date == "2023-06-11/2023-06-19"


def test_window_without_a_clear_scene_is_reported(files):
    for day in DAYS:
        files.add(scene_id(day), scl=8)
    data, outcome, limitations = fetch(files)
    assert data is None
    assert (outcome.ok, outcome.chain_step, outcome.source_name) == (False, None, None)
    assert limitations[0].affects == "current"
    assert "80% czystych pikseli" in limitations[0].text
    assert all(files.opened_layers(scene_id(day)) == {"scl"} for day in DAYS)


def test_parcel_too_small_for_a_pixel_gives_the_reason(files):
    for day in DAYS:
        files.add(scene_id(day))
    lon, lat = 18.2008, 52.7493
    tiny = GeoJsonGeometry(
        type="Polygon",
        coordinates=[
            [[lon, lat], [lon + 1e-4, lat], [lon + 1e-4, lat + 1e-4], [lon, lat + 1e-4], [lon, lat]]
        ],
    )
    data, outcome, limitations = fetch(files, outline=tiny)
    assert data is None and not outcome.ok
    assert [(limitation.text, limitation.affects) for limitation in limitations] == [
        (TOO_SMALL_TEXT, "all")
    ]
    assert outcome.message == TOO_SMALL_TEXT


def test_time_budget_cuts_the_reading_short(files):
    for day in DAYS:
        files.add(scene_id(day))

    @contextmanager
    def slow_opener(href):
        time.sleep(0.6)
        with files.opener(href) as dataset:
            yield dataset

    source = SatelliteSource(transport=catalogue(), opener=slow_opener, time_budget_s=0.2)
    started = time.monotonic()
    data, outcome, limitations = asyncio.run(source.fetch(OUTLINE, ANALYSIS_DATE))
    assert time.monotonic() - started < 0.55  # returned before the slow read ended
    assert data is None and not outcome.ok
    assert limitations[0].affects == "current"
    assert "nie zmieścił się w limicie czasu (0.2 s)" in limitations[0].text
    assert 0.2 <= outcome.duration_s < 0.55


def test_scenes_finished_within_the_budget_are_kept(files, monkeypatch):
    monkeypatch.setattr(params, "SCENES_PER_WINDOW", 2)
    for day in DAYS:
        files.add(scene_id(day))
    slow_scene = scene_id("20230616")

    @contextmanager
    def opener(href):
        if slow_scene in href and "SCL" not in href:
            time.sleep(1.0)
        with files.opener(href) as dataset:
            yield dataset

    source = SatelliteSource(transport=catalogue(), opener=opener, time_budget_s=0.5)
    data, outcome, limitations = asyncio.run(source.fetch(OUTLINE, ANALYSIS_DATE))
    assert [s.date for s in data.scenes] == [date(2023, 6, 19)]
    assert outcome.ok
    assert "limicie czasu" in limitations[0].text


@pytest.mark.parametrize("failure", [503, "connect", "not json"])
def test_catalogue_failure_gives_no_data_and_a_reason(files, failure):
    def handler(request):
        if failure == "connect":
            raise httpx.ConnectError("no route", request=request)
        if failure == "not json":
            return httpx.Response(200, text="<html>")
        return httpx.Response(failure, text="unavailable")

    data, outcome, limitations = fetch(files, transport=httpx.MockTransport(handler))
    assert data is None
    assert (outcome.topic, outcome.ok, outcome.chain_step) == ("satellite", False, None)
    assert len(limitations) == params.PREVIOUS_YEARS + 1
    assert all("nie odpowiedział" in limitation.text for limitation in limitations)
    assert files.opened == []


def test_unreadable_scene_file_is_skipped(files):
    files.add(scene_id("20230619"))
    files.add(scene_id("20230616"))
    files.add(scene_id("20230614"))
    broken = files._paths[next(h for h in files._paths if "20230619" in h and "B08" in h)]
    broken.write_bytes(b"not a raster")
    data, _, _ = fetch(files)
    assert [s.date for s in data.scenes] == [date(2023, 6, 16)]
