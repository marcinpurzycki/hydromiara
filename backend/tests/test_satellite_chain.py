"""Primary and secondary satellite service: which one answers and when the other takes over."""

import asyncio
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.sources.satellite import SatelliteSource
from app.sources.satellite_providers import EARTH_SEARCH, PLANETARY_COMPUTER
from tests.satellite_helpers import (
    OUTLINE,
    TILE_CRS,
    Deadlines,
    SceneFiles,
    recorded_answer,
    scene_id,
)

ANALYSIS_DATE = date(2023, 6, 20)
TOKEN = "sv=2025&sig=abc"
PC_ANSWER = Path(__file__).parent / "fixtures" / "planetary_computer" / "search_2023_06.json"
CHAIN = [PLANETARY_COMPUTER, EARTH_SEARCH]
PC_TILE = "34UCD"  # 23 of the 45 recorded scenes
NEWEST_SIX = [date(2023, 6, d) for d in (6, 9, 11, 14, 16, 19)]


def pc_answer() -> dict:
    return json.loads(PC_ANSWER.read_text(encoding="utf-8"))


def pc_first_copies() -> dict[str, dict]:
    """For each day of the recorded answer, the copy the adapter reads.

    The more frequent tile, the highest processing version, then the greater identifier.
    """
    by_day: dict[str, dict] = {}
    on_tile = [f for f in pc_answer()["features"] if f["properties"]["s2:mgrs_tile"] == PC_TILE]
    ranked = sorted(
        on_tile, key=lambda f: (f["properties"]["s2:processing_baseline"], f["id"]), reverse=True
    )
    for feature in ranked:
        by_day.setdefault(feature["properties"]["datetime"][:10], feature)
    return dict(sorted(by_day.items(), reverse=True))


def pc_hrefs(day: str) -> dict[str, str]:
    feature = pc_first_copies()[day]
    return {
        layer: f"{feature['assets'][name]['href']}?{TOKEN}"
        for layer, name in PLANETARY_COMPUTER.assets.items()
    }


def add_pc_scene(files: SceneFiles, day: str, **values) -> None:
    """Files of one Planetary Computer scene, under their signed addresses."""
    # Baseline 05.x: stored values carry the shift of 1000.
    values = {"red": 2000, "nir": 4000, "nir08": 4000, "swir": 3000, **values}
    files.add_hrefs(
        pc_hrefs(day), TILE_CRS[PC_TILE], label=pc_first_copies()[day]["id"], **values
    )


def services(seen: list, *, pc_search=None, pc_token=None) -> httpx.MockTransport:
    """Both services behind one transport; `seen` collects the hosts that were asked."""

    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        seen.append((host, request.url.path))
        if host == "planetarycomputer.microsoft.com" and "/sas/" in request.url.path:
            if pc_token is not None:
                return await pc_token(request)
            return httpx.Response(200, json={"token": TOKEN, "msft:expiry": "2999-01-01T00:00:00Z"})
        if host == "planetarycomputer.microsoft.com":
            if pc_search is not None:
                return await pc_search(request)
            return httpx.Response(200, json=pc_answer())
        return httpx.Response(200, json=recorded_answer())

    return httpx.MockTransport(handler)


def hosts(seen: list) -> set[str]:
    return {host for host, _ in seen}


@pytest.fixture
def files(tmp_path) -> SceneFiles:
    scenes = SceneFiles(tmp_path)
    for day in pc_first_copies():  # the same twelve days in both recorded answers
        scenes.add(scene_id(day.replace("-", "")))
        add_pc_scene(scenes, day)
    return scenes


@pytest.fixture
def deadlines():
    waits = Deadlines()
    yield waits
    waits.close()


def fetch(files: SceneFiles, transport, opener=None, **kwargs):
    kwargs.setdefault("fallback_after_s", 4.0)
    source = SatelliteSource(
        transport=transport, opener=opener or files.opener, providers=CHAIN, **kwargs
    )
    return asyncio.run(source.fetch(OUTLINE, ANALYSIS_DATE))


def values(data) -> set:
    return {(scene.ndvi, scene.ndmi) for scene in data.scenes}


async def unavailable(request):
    return httpx.Response(503, text="unavailable")


def silent(deadlines: Deadlines, then=lambda: None):
    """A search that never answers; the time limit passes while it is waited for."""

    async def handler(request):
        then()
        deadlines.fire(once="search")
        await asyncio.Event().wait()

    return handler


def test_primary_service_answers_and_the_secondary_is_not_asked(files):
    seen = []
    data, outcome, _ = fetch(files, services(seen))
    # Stored 2000/4000/3000 minus the shift give reflectance 0.1/0.3/0.2.
    assert [s.date for s in data.scenes] == NEWEST_SIX and values(data) == {(0.5, 0.2)}
    assert (outcome.ok, outcome.chain_step) == (True, 1)
    assert outcome.source_name == PLANETARY_COMPUTER.source_name
    assert hosts(seen) == {"planetarycomputer.microsoft.com"}
    assert all(href.endswith(f"?{TOKEN}") for href in files.opened)
    assert len(files.opened) == 12 + 6 * 4  # one copy a day: classification, then bands


def test_scene_whose_stored_values_do_not_fit_the_shift_is_rejected(files):
    # Reflectance of red after the shift: (900 - 1000) / 10000 < 0.
    add_pc_scene(files, "2023-06-19", red=900)
    data, _, _ = fetch(files, services([]))
    assert [s.date for s in data.scenes] == [date(2023, 6, 4), *NEWEST_SIX[:-1]]


@pytest.mark.parametrize("broken", ["pc_search", "pc_token"])
def test_failing_primary_service_is_replaced_at_once(files, deadlines, broken):
    seen = []
    # The fallback time is never fired: waiting for it would fail the test.
    data, outcome, limitations = fetch(
        files, services(seen, **{broken: unavailable}), sleep=deadlines.sleep
    )
    assert [s.date for s in data.scenes] == NEWEST_SIX and values(data) == {(0.5, 0.2)}
    assert (outcome.ok, outcome.chain_step) == (True, 2)
    assert outcome.source_name == EARTH_SEARCH.source_name
    assert "earth-search.aws.element84.com" in hosts(seen)
    # The report says what the service that answered could not deliver, nothing else.
    assert [limitation.affects for limitation in limitations] == ["multiyear"]


def test_primary_service_without_a_reading_in_time_is_replaced(files, deadlines):
    seen = []
    data, outcome, _ = fetch(
        files, services(seen, pc_search=silent(deadlines)), sleep=deadlines.sleep
    )
    assert deadlines.calls[0] == pytest.approx(4.0, abs=0.5)  # the fallback time was waited out
    assert [s.date for s in data.scenes] == NEWEST_SIX
    assert (outcome.chain_step, outcome.source_name) == (2, EARTH_SEARCH.source_name)


def test_slow_primary_service_keeps_working_once_it_has_a_reading(files, deadlines):
    broken = files._paths[pc_hrefs("2023-06-19")["nir"]]
    broken.write_bytes(b"not a raster")
    late = pc_hrefs("2023-06-04")  # read only after the six newest are done

    @contextmanager
    def opener(href):
        if href in late.values() and href != late["scl"]:
            deadlines.fire(once="late")  # the fallback time passes; five scenes are read
        with files.opener(href) as dataset:
            yield dataset

    seen = []
    data, outcome, _ = fetch(files, services(seen), opener=opener, sleep=deadlines.sleep)
    assert [s.date for s in data.scenes] == [date(2023, 6, 4), *NEWEST_SIX[:-1]]
    assert outcome.chain_step == 1
    assert hosts(seen) == {"planetarycomputer.microsoft.com"}


def test_primary_service_that_answers_with_nothing_usable_is_not_replaced(tmp_path):
    files = SceneFiles(tmp_path)
    for day in pc_first_copies():
        add_pc_scene(files, day, scl=9)  # cloud over the parcel on every day
    seen = []
    data, outcome, limitations = fetch(files, services(seen))
    assert data is None and (outcome.ok, outcome.chain_step) == (False, None)
    assert hosts(seen) == {"planetarycomputer.microsoft.com"}
    assert "czystych pikseli" in limitations[0].text


def test_both_services_failing_gives_no_data_and_a_reason(files):
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable"))
    data, outcome, limitations = fetch(files, transport)
    assert data is None and (outcome.ok, outcome.chain_step) == (False, None)
    assert [limitation.affects for limitation in limitations] == ["current", "multiyear"]
    assert all("nie odpowiedział" in limitation.text for limitation in limitations)


def test_no_time_left_for_the_secondary_service_keeps_the_primary_report(files, deadlines):
    seen, now = [], [0.0]

    def budget_spent():
        now[0] = 100.0

    data, outcome, limitations = fetch(
        files,
        services(seen, pc_search=silent(deadlines, then=budget_spent)),
        sleep=deadlines.sleep,
        clock=lambda: now[0],
    )
    assert data is None and not outcome.ok
    assert "limicie czasu" in limitations[0].text
    assert hosts(seen) == {"planetarycomputer.microsoft.com"}
    assert outcome.duration_s == 100.0


def test_archive_of_the_primary_service_reaches_further_back(files):
    seen = []
    assert PLANETARY_COMPUTER.archive_start == date(2015, 7, 11)
    assert EARTH_SEARCH.archive_start == date(2016, 11, 2)
    source = SatelliteSource(transport=services(seen), opener=files.opener, providers=CHAIN)
    data, outcome, limitations = asyncio.run(source.fetch(OUTLINE, date(2015, 6, 20)))
    assert data is None and not outcome.ok
    assert PLANETARY_COMPUTER.archive_note in limitations[0].text


def test_read_token_is_reused_between_analyses(files):
    seen = []
    source = SatelliteSource(transport=services(seen), opener=files.opener, providers=CHAIN)
    for _ in range(2):
        asyncio.run(source.fetch(OUTLINE, ANALYSIS_DATE))
    assert sum("/sas/" in path for _, path in seen) == 1

