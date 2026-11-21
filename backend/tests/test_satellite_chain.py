"""Primary and secondary satellite service: which one answers and when the other takes over."""

import asyncio
import json
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.sources import satellite_params as params
from app.sources.satellite import SatelliteSource
from app.sources.satellite_providers import EARTH_SEARCH, PLANETARY_COMPUTER
from tests.satellite_helpers import OUTLINE, TILE_CRS, SceneFiles, recorded_answer, scene_id

ANALYSIS_DATE = date(2023, 6, 20)
TOKEN = "sv=2025&sig=abc"
PC_ANSWER = Path(__file__).parent / "fixtures" / "planetary_computer" / "search_2023_06.json"
CHAIN = [PLANETARY_COMPUTER, EARTH_SEARCH]


def pc_answer() -> dict:
    return json.loads(PC_ANSWER.read_text(encoding="utf-8"))


def pc_first_copies() -> dict[str, dict]:
    """For each day of the recorded answer, the copy the adapter reads first."""
    by_day: dict[str, dict] = {}
    for feature in sorted(pc_answer()["features"], key=lambda f: f["id"], reverse=True):
        by_day.setdefault(feature["properties"]["datetime"][:10], feature)
    return by_day


def add_pc_scene(files: SceneFiles, day: str, **values) -> None:
    """Files of one Planetary Computer scene, under their signed addresses."""
    feature = pc_first_copies()[day]
    hrefs = {
        layer: f"{feature['assets'][name]['href']}?{TOKEN}"
        for layer, name in PLANETARY_COMPUTER.assets.items()
    }
    tile = next(tile for tile in TILE_CRS if f"_T{tile}_" in feature["id"])
    # Baseline 05.x: stored values carry the shift of 1000.
    values = {"red": 2000, "nir": 4000, "swir": 3000, **values}
    files.add_hrefs(hrefs, TILE_CRS[tile], label=feature["id"], **values)


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
    for day in pc_first_copies():  # the same six days in both recorded answers
        scenes.add(scene_id(day.replace("-", "")))
        add_pc_scene(scenes, day)
    return scenes


def fetch(files: SceneFiles, transport, opener=None, **kwargs):
    kwargs.setdefault("fallback_after_s", 4.0)
    source = SatelliteSource(
        transport=transport, opener=opener or files.opener, providers=CHAIN, **kwargs
    )
    return asyncio.run(source.fetch(OUTLINE, ANALYSIS_DATE))


async def unavailable(request):
    return httpx.Response(503, text="unavailable")


async def silent(request):
    await asyncio.sleep(5)
    return httpx.Response(200, json=pc_answer())


def test_primary_service_answers_and_the_secondary_is_not_asked(files):
    seen = []
    data, outcome, _ = fetch(files, services(seen))
    # Stored 2000/4000/3000 minus the shift give reflectance 0.1/0.3/0.2.
    assert [(s.date, s.ndvi, s.ndmi) for s in data.scenes] == [(date(2023, 6, 19), 0.5, 0.2)]
    assert (outcome.ok, outcome.chain_step) == (True, 1)
    assert outcome.source_name == PLANETARY_COMPUTER.source_name
    assert hosts(seen) == {"planetarycomputer.microsoft.com"}
    assert all(href.endswith(f"?{TOKEN}") for href in files.opened)


@pytest.mark.parametrize("broken", ["pc_search", "pc_token"])
def test_failing_primary_service_is_replaced_at_once(files, broken):
    seen = []
    started = time.monotonic()
    data, outcome, limitations = fetch(files, services(seen, **{broken: unavailable}))
    assert time.monotonic() - started < 2.0  # did not wait for the fallback time
    assert [(s.date, s.ndvi, s.ndmi) for s in data.scenes] == [(date(2023, 6, 19), 0.5, 0.2)]
    assert (outcome.ok, outcome.chain_step) == (True, 2)
    assert outcome.source_name == EARTH_SEARCH.source_name
    assert "earth-search.aws.element84.com" in hosts(seen)
    # The report says what the service that answered could not deliver, nothing else.
    assert [limitation.affects for limitation in limitations] == ["multiyear"] * 3


def test_primary_service_without_a_reading_in_time_is_replaced(files):
    seen = []
    started = time.monotonic()
    data, outcome, _ = fetch(files, services(seen, pc_search=silent), fallback_after_s=0.3)
    assert 0.3 <= time.monotonic() - started < 1.5
    assert [s.date for s in data.scenes] == [date(2023, 6, 19)]
    assert (outcome.chain_step, outcome.source_name) == (2, EARTH_SEARCH.source_name)


def test_slow_primary_service_keeps_working_once_it_has_a_reading(files, monkeypatch):
    monkeypatch.setattr(params, "SCENES_PER_WINDOW", 2)
    slow_scene = pc_first_copies()["2023-06-16"]["id"].split("_")[2]  # 20230616T095031

    @contextmanager
    def opener(href):
        if slow_scene in href and "_SCL_" not in href:
            time.sleep(0.5)
        with files.opener(href) as dataset:
            yield dataset

    seen = []
    data, outcome, _ = fetch(files, services(seen), opener=opener, fallback_after_s=0.3)
    assert [s.date for s in data.scenes] == [date(2023, 6, 16), date(2023, 6, 19)]
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
    assert len(limitations) == params.PREVIOUS_YEARS + 1
    assert all("nie odpowiedział" in limitation.text for limitation in limitations)


def test_no_time_left_for_the_secondary_service_keeps_the_primary_report(files):
    seen = []
    data, outcome, limitations = fetch(
        files, services(seen, pc_search=silent), time_budget_s=0.2, fallback_after_s=4.0
    )
    assert data is None and not outcome.ok
    assert "limicie czasu" in limitations[0].text
    assert hosts(seen) == {"planetarycomputer.microsoft.com"}


def test_read_token_is_reused_between_analyses(files):
    seen = []
    source = SatelliteSource(transport=services(seen), opener=files.opener, providers=CHAIN)
    for _ in range(2):
        asyncio.run(source.fetch(OUTLINE, ANALYSIS_DATE))
    assert sum("/sas/" in path for _, path in seen) == 1
