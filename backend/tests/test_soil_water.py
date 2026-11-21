"""Plant-available water computed from a soil profile."""

import json
from pathlib import Path

import pytest

from app.contracts.source_data import SoilData, SoilLayer
from app.sources import soil_params as params
from app.sources.soil import parse_response
from app.sources.soil_water import available_water_capacity, layer_available_water_mm

FIXTURES = Path(__file__).parent / "fixtures" / "soilgrids"


def layer(top: float, bottom: float, at_33: float | None, at_1500: float | None) -> SoilLayer:
    return SoilLayer(
        top_cm=top,
        bottom_cm=bottom,
        sand_pct=None,
        silt_pct=None,
        clay_pct=None,
        organic_carbon_g_kg=None,
        water_33kpa_vol_pct=at_33,
        water_1500kpa_vol_pct=at_1500,
    )


def test_layer_water_is_the_difference_times_thickness():
    # 20 % of volume over 30 cm of soil is 60 mm of water.
    assert layer_available_water_mm(layer(30, 60, 30.0, 10.0), 100) == pytest.approx((60.0, 30.0))


def test_recorded_profile_gives_the_capacity_of_one_metre():
    profile = parse_response(
        json.loads((FIXTURES / "profile_field.json").read_text(encoding="utf-8"))
    )
    capacity = available_water_capacity(profile)
    # 14.9 + 24.4 + 34.8 + 60.9 + 78.4 mm from the five recorded layers.
    assert capacity.total_mm == pytest.approx(213.4)
    assert capacity.covered_cm == 100
    assert capacity.profile_cm == params.PROFILE_DEPTH_CM
    assert capacity.complete
    assert capacity.mm_per_m == pytest.approx(213.4)


def test_layers_without_water_content_lower_the_coverage():
    soil = SoilData(
        layers=[
            layer(0, 30, 30.0, 10.0),
            layer(30, 60, None, 10.0),
            layer(60, 100, 25.0, None),
        ]
    )
    capacity = available_water_capacity(soil)
    assert capacity.total_mm == pytest.approx(60.0)
    assert capacity.covered_cm == 30
    assert not capacity.complete
    assert capacity.mm_per_m == pytest.approx(200.0)


def test_profile_depth_cuts_layers():
    soil = SoilData(layers=[layer(0, 30, 30.0, 10.0), layer(30, 60, 30.0, 10.0)])
    capacity = available_water_capacity(soil, profile_cm=45)
    assert capacity.total_mm == pytest.approx(90.0)
    assert capacity.covered_cm == 45
    assert capacity.complete
    assert available_water_capacity(soil, profile_cm=30).total_mm == pytest.approx(60.0)


def test_layer_drier_at_33_than_at_1500_kpa_is_not_used():
    soil = SoilData(layers=[layer(0, 30, 8.0, 10.0), layer(30, 60, 30.0, 10.0)])
    capacity = available_water_capacity(soil)
    assert capacity.total_mm == pytest.approx(60.0)
    assert capacity.covered_cm == 30


def test_profile_without_usable_layers_has_no_capacity():
    assert available_water_capacity(SoilData(layers=[])) is None
    assert available_water_capacity(SoilData(layers=[layer(0, 30, None, None)])) is None
