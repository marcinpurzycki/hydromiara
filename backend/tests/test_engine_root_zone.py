"""Root zone capacity, stress coefficient and engine parameters."""

import dataclasses
from pathlib import Path

import pytest

from app.engine import params as engine_params
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.root_zone import RootZone, root_depth_cm, root_zone
from app.engine import soil_capacity
from tests.engine_helpers import BARE_FIELD, SIMPLE_BARE_ZONE, SIMPLE_ZONE, WHEAT, recorded_soil
from tests.soil_helpers import recorded_layers, soil_with

ENGINE_DIR = Path(engine_params.__file__).parent


def test_working_values_are_the_agreed_ones():
    assert DEFAULT_PARAMS.deficit_year_min_stress_days == 10
    assert DEFAULT_PARAMS.current_level_min_ks == (1.0, 0.75, 0.4)
    assert DEFAULT_PARAMS.susceptibility_level_min_years == (3, 5, 8)
    assert DEFAULT_PARAMS.root_zone_limit_cm == soil_capacity.PROFILE_DEPTH_CM == 100.0
    # The deep end of the tabulated rooting depth: rainfed crops (FAO-56 Table 22).
    assert DEFAULT_PARAMS.root_depth_range_end == 1
    assert DEFAULT_PARAMS.window_years == 10
    assert engine_params.DEFICIT_LEVEL_LABELS == (
        "w normie",
        "lekki niedobór",
        "wyraźny niedobór",
        "silny niedobór",
    )


def test_every_parameter_field_has_a_module_constant():
    for field in dataclasses.fields(EngineParams):
        if field.name == "bare_soil_kc":
            continue
        assert getattr(engine_params, field.name.upper()) == field.default


@pytest.mark.parametrize(
    "changes",
    [
        {"current_level_min_ks": (1.0, 0.4, 0.75)},
        {"current_level_min_ks": (1.2, 0.75, 0.4)},
        {"susceptibility_level_min_years": (5, 3, 8)},
        {"initial_depletion_share": 1.5},
        {"root_zone_limit_cm": 0.0},
        {"climatic_balance_months": (7, 4)},
        {"deficit_year_min_stress_days": 0},
        {"root_depth_range_end": 2},
    ],
)
def test_inconsistent_parameters_are_rejected(changes):
    with pytest.raises(ValueError):
        EngineParams(**changes)


def test_wheat_roots_are_limited_to_the_soil_data_depth():
    assert root_depth_cm(WHEAT) == (100.0, True)
    shallow_end = EngineParams(root_zone_limit_cm=160.0, root_depth_range_end=0)
    assert root_depth_cm(WHEAT, shallow_end) == (150.0, False)
    assert root_depth_cm(WHEAT, EngineParams(root_zone_limit_cm=200.0)) == (180.0, False)


def test_recorded_soil_gives_the_root_zone_of_wheat():
    zone = root_zone(recorded_soil(), WHEAT)
    assert zone.capacity_source == "iung_category"
    assert zone.depth_cm == 100.0
    # Category III of the map: 186 mm per metre over the 100 cm root zone.
    assert zone.taw_mm == pytest.approx(186.0)
    assert zone.depletion_fraction == 0.55
    assert zone.raw_mm == pytest.approx(0.55 * 186.0)
    assert zone.limited_by_profile
    assert (zone.soil.category, zone.soil.estimated_category) == (3, 2)


def test_missing_soil_uses_the_flagged_fallback():
    zone = root_zone(None, WHEAT)
    assert zone.capacity_source == "fallback"
    assert zone.taw_mm == pytest.approx(engine_params.FALLBACK_AVAILABLE_WATER_MM_PER_M)
    changed = root_zone(None, WHEAT, EngineParams(fallback_available_water_mm_per_m=120.0))
    assert changed.taw_mm == pytest.approx(120.0)


def test_each_chain_link_gives_its_capacity_source():
    by_map = root_zone(soil_with({1: 100.0}), WHEAT)
    assert (by_map.capacity_source, by_map.taw_mm) == ("iung_category", pytest.approx(110.0))
    estimated = root_zone(soil_with({}, {11: 100.0}, recorded_layers()), WHEAT)
    assert (estimated.capacity_source, estimated.taw_mm) == (
        "texture_estimate",
        pytest.approx(149.0),
    )
    nothing = root_zone(soil_with({}, {13: 100.0}), WHEAT)
    assert (nothing.capacity_source, nothing.taw_mm) == ("fallback", pytest.approx(150.0))


def test_capacity_per_metre_is_scaled_to_a_shallower_root_zone():
    zone = root_zone(soil_with({4: 100.0}), WHEAT, EngineParams(root_zone_limit_cm=60.0))
    assert (zone.depth_cm, zone.taw_mm) == (60.0, pytest.approx(132.0))
    assert zone.available_water_mm_per_m == pytest.approx(220.0)


def test_bare_field_has_the_whole_profile_and_no_depletion_fraction():
    zone = root_zone(recorded_soil(), BARE_FIELD)
    assert zone.depth_cm == 100.0
    assert zone.depletion_fraction is None
    assert zone.raw_mm is None
    assert not zone.limited_by_profile


@pytest.mark.parametrize(
    ("depletion", "expected"),
    [(0.0, 1.0), (50.0, 1.0), (62.5, 0.75), (80.0, 0.4), (100.0, 0.0), (120.0, 0.0)],
)
def test_stress_coefficient_follows_the_depletion(depletion, expected):
    # TAW 100, RAW 50: Ks = (100 - Dr) / 50 above RAW.
    assert SIMPLE_ZONE.stress_coefficient(depletion) == pytest.approx(expected)


def test_no_stress_coefficient_without_a_crop():
    assert SIMPLE_BARE_ZONE.stress_coefficient(99.0) == 1.0
    assert not SIMPLE_BARE_ZONE.is_stressed(99.0)


@pytest.mark.parametrize(
    "arguments",
    [
        {"depth_cm": 100.0, "taw_mm": 0.0, "depletion_fraction": 0.5},
        {"depth_cm": 0.0, "taw_mm": 100.0, "depletion_fraction": 0.5},
        {"depth_cm": 100.0, "taw_mm": 100.0, "depletion_fraction": 1.0},
    ],
)
def test_impossible_root_zone_is_rejected(arguments):
    with pytest.raises(ValueError):
        RootZone(**arguments)


def test_engine_has_no_network_clock_or_storage():
    forbidden = (
        "httpx",
        "requests",
        "urllib",
        "socket",
        "sqlite",
        "random",
        "import time",
        "import os",
        ".now(",
        ".today(",
        "open(",
    )
    for path in sorted(ENGINE_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        found = [word for word in forbidden if word in text]
        assert not found, f"{path.name} uses {found}"
        assert len(text.splitlines()) <= 250, f"{path.name} is longer than 250 lines"
