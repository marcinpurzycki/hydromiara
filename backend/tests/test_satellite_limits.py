"""Time limit and archive reach of the satellite adapter; no real waiting."""

import asyncio
import json
from contextlib import contextmanager
from datetime import date

import pytest

from app.sources import satellite_params as params
from app.sources.satellite import SatelliteSource
from app.sources.satellite_providers import EARTH_SEARCH
from tests.satellite_helpers import (
    DAYS,
    OUTLINE,
    Deadlines,
    SceneFiles,
    catalogue,
    scene_id,
)

ANALYSIS_DATE = date(2023, 6, 20)
NEWEST_SIX = [date(2023, 6, d) for d in (6, 9, 11, 14, 16, 19)]


@pytest.fixture
def files(tmp_path) -> SceneFiles:
    return SceneFiles(tmp_path)


@pytest.fixture
def deadlines():
    waits = Deadlines()
    yield waits
    waits.close()


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


def test_window_before_the_archive_is_not_asked_and_is_named(files):
    add_all(files)
    seen = []
    data, _, limitations = fetch(files, date(2017, 3, 1), transport=catalogue(seen=seen))
    # Earth Search begins on 02.11.2016: only the current window can hold scenes.
    assert [json.loads(r.content)["datetime"][:10] for r in seen] == ["2017-01-30"]
    assert data is None
    assert [limitation.affects for limitation in limitations] == ["current", "multiyear"]
    history = limitations[1].text
    assert "2012, 2013, 2014, 2015, 2016 (przed początkiem archiwum zdjęć)" in history
    assert EARTH_SEARCH.archive_note in history
    seen.clear()
    data, outcome, limitations = fetch(files, date(2016, 6, 20), transport=catalogue(seen=seen))
    assert seen == [] and data is None and not outcome.ok
    assert EARTH_SEARCH.archive_note in limitations[0].text


def test_time_limit_cuts_the_reading_short(files, deadlines):
    add_all(files)

    @contextmanager
    def stuck(href):
        deadlines.fire()  # the limit passes while the first file is being read
        deadlines.hold()
        with files.opener(href) as dataset:
            yield dataset

    data, outcome, limitations = fetch(files, opener=stuck, sleep=deadlines.sleep)
    assert params.TIME_BUDGET_S == 12.0
    assert deadlines.calls == [pytest.approx(12.0, abs=0.5)]
    assert data is None and not outcome.ok
    assert limitations[0].affects == "current"
    assert "nie zmieścił się w limicie czasu (12 s)" in limitations[0].text


def test_scenes_finished_before_the_time_limit_are_kept(files, deadlines):
    add_all(files)
    broken = files._paths[next(h for h in files._paths if "33UYU_20230619" in h and "B08" in h)]
    broken.write_bytes(b"not a raster")
    replacement = scene_id("20230604")  # read only after the six newest are done

    @contextmanager
    def opener(href):
        if replacement in href and "SCL" not in href:
            deadlines.fire()
            deadlines.hold()
        with files.opener(href) as dataset:
            yield dataset

    data, outcome, limitations = fetch(files, opener=opener, sleep=deadlines.sleep)
    assert [s.date for s in data.scenes] == NEWEST_SIX[:-1]
    assert outcome.ok
    assert "przerwał limit czasu (12 s)" in limitations[0].text
    assert "wykorzystano zdjęcia odczytane" in limitations[0].text


def test_duration_comes_from_the_clock_of_the_adapter(files):
    add_all(files)
    ticks = iter(range(0, 1000, 5))
    _, outcome, _ = fetch(files, clock=lambda: float(next(ticks)))
    assert outcome.duration_s > 0 and outcome.duration_s % 5 == 0
