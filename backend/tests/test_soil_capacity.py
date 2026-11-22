"""Water capacity of the soil: category table, texture equations, the choice between them."""

import json
from pathlib import Path

import pytest

from app.contracts.source_data import SoilData, SoilLayer, SourceData
from app.engine import soil_capacity as capacity
from app.engine.soil_capacity import (
    category_map_decides,
    estimated_category,
    layer_capacity_mm_per_m,
    profile_capacity_mm_per_m,
    soil_capacity,
)
from tests.soil_helpers import recorded_layers, recorded_soil, soil_with

FIXTURES = Path(__file__).parent / "fixtures"
FALLBACK = 150.0


def profile(sand: float, clay: float, carbon: float, bottom: float = 100.0) -> list[SoilLayer]:
    return [
        SoilLayer(
            top_cm=0.0, bottom_cm=bottom, sand_pct=sand, silt_pct=100.0 - sand - clay,
            clay_pct=clay, organic_carbon_g_kg=carbon,
            water_33kpa_vol_pct=None, water_1500kpa_vol_pct=None,
        )  # fmt: skip
    ]


def test_working_values_are_the_agreed_ones():
    assert capacity.CATEGORY_CAPACITY_MM_PER_M == {1: 110.0, 2: 149.0, 3: 186.0, 4: 220.0}
    assert capacity.ESTIMATED_CATEGORY_FROM_MM_PER_M == (85.0, 113.0, 135.0)
    assert capacity.MAX_ORGANIC_MATTER_PCT == 3.5
    assert capacity.MIN_DECIDING_SHARE_PCT == 50.0
    assert capacity.DIVERGENT_FROM_CATEGORIES == 2
    assert capacity.PROFILE_DEPTH_CM == 100.0


def test_layer_capacity_follows_the_equations_by_hand():
    # Sand 66 %, clay 13 %, organic carbon 8.7 g/kg -> organic matter 8.7 * 0.1 / 0.58 = 1.5 %.
    # Wilting point: -0.024*0.66 + 0.487*0.13 + 0.006*1.5 + 0.005*0.66*1.5 - 0.013*0.13*1.5
    #   + 0.068*0.66*0.13 + 0.031 = 0.095719; 0.095719 + (0.14*0.095719 - 0.02) = 0.089120.
    # Field capacity: -0.251*0.66 + 0.195*0.13 + 0.011*1.5 + 0.006*0.66*1.5 - 0.027*0.13*1.5
    #   + 0.452*0.66*0.13 + 0.299 = 0.214647;
    #   0.214647 + (1.283*0.214647**2 - 0.374*0.214647 - 0.015) = 0.178481.
    # Capacity: (0.178481 - 0.089120) * 1000 = 89.4 mm per metre.
    assert layer_capacity_mm_per_m(66.0, 13.0, 8.7) == pytest.approx(89.36, abs=0.01)
    # Heavier soils hold more, sands less.
    assert layer_capacity_mm_per_m(90.0, 3.0, 5.0) == pytest.approx(45.1, abs=0.1)
    assert layer_capacity_mm_per_m(21.0, 35.0, 12.0) == pytest.approx(151.2, abs=0.1)


def test_organic_matter_is_capped():
    # 3.5 % of organic matter is 20.3 g/kg of carbon; more carbon changes nothing.
    assert layer_capacity_mm_per_m(70.4, 9.3, 51.3) == pytest.approx(
        layer_capacity_mm_per_m(70.4, 9.3, 20.3)
    )
    assert layer_capacity_mm_per_m(70.4, 9.3, 10.0) < layer_capacity_mm_per_m(70.4, 9.3, 20.3)


def test_recorded_texture_gives_the_estimated_category():
    soil = SoilData(layers=recorded_layers())
    # (92.4*5 + 84.7*10 + 86.6*15 + 91.9*30 + 93.7*40) / 100 = 91.2 mm per metre.
    assert profile_capacity_mm_per_m(soil) == pytest.approx(91.2, abs=0.1)
    assert estimated_category(soil) == 2


@pytest.mark.parametrize(
    ("sand", "clay", "carbon", "category"),
    [(90.0, 3.0, 5.0, 1), (66.0, 13.0, 8.7, 2), (55.0, 16.0, 9.0, 2), (40.0, 20.0, 10.0, 4),
     (21.0, 35.0, 12.0, 4)],
)  # fmt: skip
def test_estimated_category_by_texture(sand, clay, carbon, category):
    assert estimated_category(SoilData(layers=profile(sand, clay, carbon))) == category


def test_bounds_of_the_estimated_categories(monkeypatch):
    soil = SoilData(layers=profile(55.0, 16.0, 9.0))  # 110.7 mm per metre
    for bounds, category in (
        ((111.0, 113.0, 135.0), 1), ((85.0, 113.0, 135.0), 2), ((85.0, 110.0, 135.0), 3),
        ((85.0, 100.0, 110.0), 4),
    ):  # fmt: skip
        monkeypatch.setattr(capacity, "ESTIMATED_CATEGORY_FROM_MM_PER_M", bounds)
        assert estimated_category(soil) == category


def test_texture_must_cover_the_whole_profile():
    assert estimated_category(SoilData(layers=profile(66.0, 13.0, 8.7, bottom=60.0))) is None
    assert estimated_category(SoilData(layers=[])) is None
    layers = recorded_layers()
    gap = layers[2].model_copy(update={"organic_carbon_g_kg": None})
    assert estimated_category(SoilData(layers=[*layers[:2], gap, *layers[3:]])) is None
    # Layers below the profile depth are not needed and not used.
    deeper = profile(10.0, 60.0, 5.0)[0].model_copy(update={"top_cm": 100.0, "bottom_cm": 200.0})
    assert estimated_category(SoilData(layers=[*layers, deeper])) == 2


def test_link_1_capacity_comes_from_the_category_table():
    for category, mm_per_m in capacity.CATEGORY_CAPACITY_MM_PER_M.items():
        found = soil_capacity(soil_with({category: 100.0}), FALLBACK)
        assert (found.source, found.mm_per_m, found.category) == (
            "iung_category", mm_per_m, category,
        )  # fmt: skip
        assert found.map_read and not found.mixed and not found.divergent


def test_mixed_parcel_gets_the_capacity_weighted_by_the_points():
    # 5 points of category III and 4 of category I: (186*5 + 110*4) / 9 = 152.2.
    found = soil_capacity(soil_with({3: 55.6, 1: 44.4}), FALLBACK)
    assert found.mm_per_m == pytest.approx(152.2, abs=0.1)
    assert (found.category, found.shares, found.mixed) == (3, ((3, 55.6), (1, 44.4)), True)
    # Points without a category do not take part in the mean.
    partly = soil_capacity(soil_with({2: 40.0, 4: 20.0}, {11: 40.0}), FALLBACK)
    assert partly.mm_per_m == pytest.approx((149 * 40 + 220 * 20) / 60)
    # With equal shares the more susceptible category names the parcel.
    assert soil_capacity(soil_with({4: 50.0, 2: 50.0}), FALLBACK).category == 2


def test_map_decides_from_half_of_the_points():
    layers = recorded_layers()
    half = soil_with({3: 50.0}, {11: 50.0}, layers)
    below = soil_with({3: 48.0}, {11: 52.0}, layers)
    assert category_map_decides(half) and not category_map_decides(below)
    assert soil_capacity(half, FALLBACK).source == "iung_category"
    estimated = soil_capacity(below, FALLBACK)
    # Link 2: the capacity of the estimated category, not the equation value.
    assert (estimated.source, estimated.category, estimated.mm_per_m) == (
        "texture_estimate", 2, 149.0,
    )  # fmt: skip
    assert estimated.map_read
    not_read = soil_capacity(soil_with(layers=layers, map_read=False), FALLBACK)
    assert (not_read.source, not_read.map_read) == ("texture_estimate", False)


def test_link_3_is_the_stand_in_value():
    for soil in (None, soil_with({}, {13: 100.0}), soil_with({1: 20.0}, {12: 80.0}),
                 SoilData(layers=[])):  # fmt: skip
        found = soil_capacity(soil, FALLBACK)
        assert (found.source, found.mm_per_m, found.category) == ("fallback", FALLBACK, None)
        assert not found.organic


def test_organic_soil_is_not_estimated_from_texture():
    organic = soil_with({2: 20.0}, {5: 80.0}, recorded_layers())
    assert category_map_decides(organic)
    found = soil_capacity(organic, FALLBACK)
    assert (found.source, found.mm_per_m, found.organic) == ("fallback", FALLBACK, True)
    # A few organic points on a classified parcel change nothing.
    recorded = soil_capacity(recorded_soil(), FALLBACK)
    assert (recorded.source, recorded.mm_per_m, recorded.organic) == ("iung_category", 186.0, False)


def test_sources_two_categories_apart_are_divergent():
    layers = recorded_layers()  # estimated category II
    assert soil_capacity(soil_with({4: 100.0}, layers=layers), FALLBACK).divergent
    assert not soil_capacity(soil_with({3: 100.0}, layers=layers), FALLBACK).divergent
    assert not soil_capacity(soil_with({4: 100.0}), FALLBACK).divergent
    sandy = profile(90.0, 3.0, 5.0)  # estimated category I
    assert soil_capacity(soil_with({3: 100.0}, layers=sandy), FALLBACK).divergent
    assert not soil_capacity(soil_with({}, {11: 100.0}, sandy), FALLBACK).divergent


def test_soil_stored_before_the_categories_is_estimated_from_its_texture():
    raw = (FIXTURES / "stored" / "source_data_before_soil_categories.json").read_text()
    soil = SourceData.model_validate_json(raw).soil
    found = soil_capacity(soil, FALLBACK)
    assert (found.source, found.map_read) == ("texture_estimate", False)
    assert found.mm_per_m in capacity.CATEGORY_CAPACITY_MM_PER_M.values()
    # The stored water contents are not used: without them the result is the same.
    bare = SoilData(
        layers=[
            layer.model_copy(update={"water_33kpa_vol_pct": None, "water_1500kpa_vol_pct": None})
            for layer in soil.layers
        ]
    )
    assert soil_capacity(bare, FALLBACK) == found
    assert json.loads(raw)["soil"]["layers"][0]["water_33kpa_vol_pct"] is not None
