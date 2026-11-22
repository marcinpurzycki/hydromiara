"""The two satellite services: reflectance offset rules and project configuration."""

import copy
from datetime import date

import pytest

from app.sources import satellite_providers as providers
from app.sources.satellite_providers import EARTH_SEARCH, PLANETARY_COMPUTER
from app.sources.satellite_search import SearchWindow, parse_items, search_body
from tests.satellite_helpers import OUTLINE, recorded_answer
from tests.test_satellite_chain import pc_answer

JUNE = SearchWindow(start=date(2023, 6, 5), end=date(2023, 6, 20), anchor=date(2023, 6, 20))


@pytest.mark.parametrize(
    ("baseline", "offset"),
    [("02.12", 0.0), ("03.01", 0.0), ("04.00", -0.1), ("05.09", -0.1), ("05.11", -0.1)],
)
def test_planetary_computer_shift_applies_from_baseline_04(baseline, offset):
    found = providers.planetary_computer_offset({"s2:processing_baseline": baseline})
    assert found == pytest.approx(offset)


@pytest.mark.parametrize(
    ("properties", "offset"),
    [
        ({"s2:processing_baseline": "02.14", "earthsearch:boa_offset_applied": False}, 0.0),
        ({"s2:processing_baseline": "05.00", "earthsearch:boa_offset_applied": True}, 0.0),
        ({"s2:processing_baseline": "04.00", "earthsearch:boa_offset_applied": False}, None),
        ({"s2:processing_baseline": "05.10"}, None),
    ],
)
def test_earth_search_scene_with_an_untold_shift_is_skipped(properties, offset):
    assert providers.earth_search_offset(properties) == offset


@pytest.mark.parametrize(
    "rule", [providers.planetary_computer_offset, providers.earth_search_offset]
)
def test_scene_without_a_processing_version_is_skipped(rule):
    assert rule({}) is None and rule({"s2:processing_baseline": None}) is None


def test_recorded_planetary_computer_answer_is_read_with_token_and_offset():
    items = parse_items(pc_answer(), JUNE, PLANETARY_COMPUTER, token="t=1")
    assert len(items) == 23
    assert {item.date for item in items} == {date(2023, 6, d) for d in (6, 9, 11, 14, 16, 19)}
    assert all(set(item.hrefs) == {"scl", "red", "nir", "nir08", "swir16"} for item in items)
    assert all(href.endswith(".tif?t=1") for item in items for href in item.hrefs.values())
    assert all(item.reflectance_offset == pytest.approx(-0.1) for item in items)


def test_earth_search_scene_with_files_outside_https_is_left_out():
    payload = copy.deepcopy(recorded_answer())
    payload["features"][0]["assets"]["red"]["href"] = "s3://bucket/B04.jp2"
    payload["features"][1]["properties"]["earthsearch:boa_offset_applied"] = False
    items = parse_items(payload, JUNE, EARTH_SEARCH)
    assert len(items) == 10
    assert {item.reflectance_offset for item in items} == {0.0}


def test_each_service_is_asked_for_its_own_files_and_properties():
    geometry = OUTLINE.model_dump()
    pc = search_body(PLANETARY_COMPUTER, geometry, JUNE)["fields"]
    es = search_body(EARTH_SEARCH, geometry, JUNE)["fields"]
    assert {"assets.B04.href", "assets.SCL.href", "properties.s2:processing_baseline"} <= set(
        pc["include"]
    )
    assert {"assets.red.href", "properties.earthsearch:boa_offset_applied"} <= set(es["include"])
    assert "assets.visual" in es["exclude"] and "assets.red-jp2" in es["exclude"]
    assert not any(field.startswith("assets.red.href") for field in es["exclude"])


def test_project_decision_is_planetary_computer_first_earth_search_second():
    assert providers.configured_chain({}) == [PLANETARY_COMPUTER, EARTH_SEARCH]
    assert providers.configured_fallback_after_s({}) == 4.0


def test_configuration_can_swap_or_drop_the_services():
    swapped = {"SATELLITE_PRIMARY": "earth-search", "SATELLITE_SECONDARY": "planetary-computer"}
    assert providers.configured_chain(swapped) == [EARTH_SEARCH, PLANETARY_COMPUTER]
    assert providers.configured_chain({"SATELLITE_SECONDARY": "none"}) == [PLANETARY_COMPUTER]
    same = {"SATELLITE_PRIMARY": "earth-search", "SATELLITE_SECONDARY": "earth-search"}
    assert providers.configured_chain(same) == [EARTH_SEARCH]
    assert providers.configured_fallback_after_s({"SATELLITE_FALLBACK_AFTER_S": "2.5"}) == 2.5


@pytest.mark.parametrize(
    "env",
    [{"SATELLITE_PRIMARY": "landsat"}, {"SATELLITE_SECONDARY": "Earth Search"}],
)
def test_unknown_service_name_is_refused(env):
    with pytest.raises(ValueError, match="unknown satellite service"):
        providers.configured_chain(env)


@pytest.mark.parametrize("value", ["0", "-1", "soon"])
def test_fallback_time_must_be_a_positive_number(value):
    with pytest.raises(ValueError, match="positive number"):
        providers.configured_fallback_after_s({"SATELLITE_FALLBACK_AFTER_S": value})


def test_each_service_reads_with_its_own_number_of_threads():
    assert (PLANETARY_COMPUTER.read_workers, EARTH_SEARCH.read_workers) == (16, 32)
    assert (PLANETARY_COMPUTER.page_limit, EARTH_SEARCH.page_limit) == (1000, 2000)
