"""Satellite adapter on a recorded catalogue answer and scene files built in the test."""

import asyncio
import json
from datetime import date

import httpx
import pytest

from app.sources import satellite_params as params
from app.sources.satellite import SatelliteSource
from app.sources.satellite_limitations import NARROW_TEXT, TOO_SMALL_TEXT
from app.sources.satellite_providers import EARTH_SEARCH
from tests.satellite_helpers import (
    DAYS,
    NARROW,
    OUTLINE,
    TINY,
    SceneFiles,
    catalogue,
    scene_id,
)

ANALYSIS_DATE = date(2023, 6, 20)
NEWEST_SIX = [date(2023, 6, d) for d in (6, 9, 11, 14, 16, 19)]


@pytest.fixture
def files(tmp_path) -> SceneFiles:
    return SceneFiles(tmp_path)


def add_all(files: SceneFiles, **values) -> None:
    for day in DAYS:
        files.add(scene_id(day), **values)


def fetch(files: SceneFiles, analysis_date: date = ANALYSIS_DATE, outline=OUTLINE, **kwargs):
    source = SatelliteSource(
        transport=kwargs.pop("transport", None) or catalogue(),
        opener=kwargs.pop("opener", None) or files.opener,
        providers=[EARTH_SEARCH],
        **kwargs,
    )
    return asyncio.run(source.fetch(outline, analysis_date))


def test_six_newest_clear_scenes_of_the_current_window_are_read(files):
    add_all(files)
    data, outcome, limitations = fetch(files)
    assert [s.date for s in data.scenes] == NEWEST_SIX
    assert {(s.clear_share_pct, s.ndvi, s.ndmi) for s in data.scenes} == {(100.0, 0.5, 0.2)}
    assert (outcome.topic, outcome.ok, outcome.chain_step) == ("satellite", True, 1)
    assert outcome.source_name == EARTH_SEARCH.source_name
    assert outcome.data_date == "2023-06-06/2023-06-19"
    # The recorded answer has no scenes for the five earlier years: one limitation for all.
    assert [limitation.affects for limitation in limitations] == ["multiyear"]
    assert "2018, 2019, 2020, 2021, 2022 (brak zdjęć w katalogu)" in limitations[0].text
    assert outcome.message == limitations[0].text


def test_classification_is_read_for_every_day_and_bands_only_for_the_chosen_scenes(files):
    add_all(files)
    fetch(files)
    assert len(files.opened) == len(set(files.opened))  # nothing is opened twice
    for day in DAYS[:6]:
        assert files.opened_layers(scene_id(day)) == {"scl", "red", "nir", "nir08", "swir16"}
    for day in DAYS[6:]:
        assert files.opened_layers(scene_id(day)) == {"scl"}
    # The copy of each day on the other tile is never touched.
    assert all(files.opened_layers(scene_id(day, tile="34UCD")) == set() for day in DAYS)


def test_cloudy_scene_is_skipped_without_reading_its_bands(files):
    add_all(files)
    files.add(scene_id("20230619"), scl=9)  # cloud over the whole parcel
    data, _, _ = fetch(files)
    assert [s.date for s in data.scenes] == [date(2023, 6, 4), *NEWEST_SIX[:-1]]
    assert files.opened_layers(scene_id("20230619")) == {"scl"}


def test_scene_that_cannot_be_read_is_replaced_by_the_next_clear_one(files):
    add_all(files)
    broken = files._paths[next(h for h in files._paths if "33UYU_20230619" in h and "B08" in h)]
    broken.write_bytes(b"not a raster")
    data, _, _ = fetch(files)
    assert [s.date for s in data.scenes] == [date(2023, 6, 4), *NEWEST_SIX[:-1]]


def test_no_scene_after_the_analysis_date_is_read(files):
    add_all(files)
    seen = []
    data, _, _ = fetch(files, date(2023, 6, 12), transport=catalogue(seen=seen))
    assert max(s.date for s in data.scenes) == date(2023, 6, 11)
    assert len(data.scenes) == params.CURRENT_SCENES
    for later in ("20230619", "20230616", "20230614"):
        assert files.opened_layers(scene_id(later)) == set()
    ranges = [json.loads(request.content)["datetime"] for request in seen]
    assert len(ranges) == 1 + params.HISTORY_YEARS
    assert max(searched.split("/")[1] for searched in ranges) == "2023-06-12T23:59:59Z"
    assert all(request.headers["user-agent"] == "hydro-analysis/0.1" for request in seen)


@pytest.mark.parametrize(("analysis_date", "found"), [(date(2023, 6, 21), True), (date(2023, 6, 22), False)])
def test_current_window_reaches_30_days_back(files, analysis_date, found):
    add_all(files, scl=9)
    files.add(scene_id("20230522"))  # the only clear day, 30 and 31 days before the dates
    data, _, limitations = fetch(files, analysis_date)
    assert (data is not None) == found
    if not found:
        assert "23.05.2023–22.06.2023" in limitations[0].text


def test_earlier_year_gives_its_two_clear_scenes_nearest_to_the_same_day(files):
    add_all(files)
    data, _, limitations = fetch(files, transport=catalogue(years=(2022, 2020)))
    by_year = {year: [s.date for s in data.scenes if s.date.year == year] for year in (2020, 2022)}
    # Window 05.06-05.07 around 20.06: of the days 6, 9, 11, 14, 16, 19 June the nearest two.
    assert by_year[2022] == [date(2022, 6, 16), date(2022, 6, 19)]
    assert by_year[2020] == [date(2020, 6, 16), date(2020, 6, 19)]
    assert len(data.scenes) == 6 + 2 + 2 <= params.MAX_SCENES
    assert "2018, 2019, 2021 (brak zdjęć w katalogu)" in limitations[0].text


def test_all_windows_together_never_give_more_than_sixteen_scenes(files):
    add_all(files)
    data, _, limitations = fetch(files, transport=catalogue(years=(2022, 2021, 2020, 2019, 2018)))
    assert len(data.scenes) == 16 == params.MAX_SCENES
    assert limitations == []
    assert [s.date for s in data.scenes] == sorted(s.date for s in data.scenes)


def test_reading_is_repeatable(files):
    add_all(files)
    transport = catalogue(years=(2022, 2021))
    first, second = fetch(files, transport=transport), fetch(files, transport=transport)
    assert first.data == second.data and first.limitations == second.limitations


def test_window_without_a_clear_scene_is_reported_once(files):
    add_all(files, scl=8)
    data, outcome, limitations = fetch(files)
    assert data is None
    assert (outcome.ok, outcome.chain_step, outcome.source_name) == (False, None, None)
    assert [limitation.affects for limitation in limitations] == ["current", "multiyear"]
    assert "95% czystych pikseli" in limitations[0].text
    assert "21.05.2023–20.06.2023" in limitations[0].text
    assert all(files.opened_layers(scene_id(day)) == {"scl"} for day in DAYS)


def test_parcel_too_small_for_either_index_gives_the_reason(files):
    add_all(files)
    data, outcome, limitations = fetch(files, outline=TINY)
    assert data is None and not outcome.ok
    assert [(limitation.text, limitation.affects) for limitation in limitations] == [
        (TOO_SMALL_TEXT, "all")
    ]
    assert outcome.message == TOO_SMALL_TEXT


def test_narrow_parcel_gives_ndvi_without_ndmi_and_says_so(files):
    add_all(files)
    data, outcome, limitations = fetch(files, outline=NARROW)
    assert outcome.ok and len(data.scenes) == params.CURRENT_SCENES
    assert {(s.ndvi, s.ndmi) for s in data.scenes} == {(0.5, None)}
    assert (limitations[0].text, limitations[0].affects) == (NARROW_TEXT, "current")
    assert files.opened_layers(scene_id("20230619")) == {"scl", "red", "nir"}


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
    assert [limitation.affects for limitation in limitations] == ["current", "multiyear"]
    assert "nie odpowiedział" in limitations[0].text
    assert "katalog zdjęć nie odpowiedział" in limitations[1].text
    assert files.opened == []
