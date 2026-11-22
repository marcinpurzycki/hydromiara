"""Crop catalogue: completeness, provenance of every value, lookup, contract shape."""

import inspect
import re
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.catalog import (
    crop_data,
    crop_data_cereals,
    crop_data_field_crops,
    crop_data_vegetables,
    crops,
)
from app.catalog.crop_model import CatalogCrop, CropGrowth, Sourced
from app.contracts.catalog import Crop
from app.mock import data as mock_data

DATA_MODULES = (crop_data_cereals, crop_data_field_crops, crop_data_vegetables)
ALL_CROPS = crops.list_crops()
GROWING = [crop for crop in ALL_CROPS if crop.growth is not None]


def test_list_holds_winter_wheat_and_exactly_one_bare_field():
    assert crops.has_crop("winter_wheat")
    assert [crop.id for crop in ALL_CROPS if crop.is_bare_field] == ["bare_field"]
    assert crops.get_crop("bare_field").name == "Pole bez uprawy"


def test_identifiers_and_names_are_unique():
    assert len({crop.id for crop in ALL_CROPS}) == len(ALL_CROPS)
    assert len({crop.name for crop in ALL_CROPS}) == len(ALL_CROPS)
    assert len({crop.name_genitive for crop in ALL_CROPS}) == len(ALL_CROPS)
    for crop in ALL_CROPS:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", crop.id), crop.id


def test_list_and_default_tiles():
    assert len(ALL_CROPS) == 22 and ALL_CROPS[-1].is_bare_field
    assert {crop.id for crop in ALL_CROPS if crop.tile} == {
        "winter_wheat",
        "maize",
        "winter_rapeseed",
        "spring_barley",
        "winter_rye",
        "bare_field",
    }
    assert {crop.id for crop in ALL_CROPS if crop.conditional} == {
        "winter_rye",
        "winter_triticale",
        "winter_rapeseed",
        "grassland",
        "cereal_mix",
        "onion",
        "cabbage",
        "beetroot",
        "tomato",
        "cucumber",
    }
    assert [crop.id for crop in ALL_CROPS if crop.perennial] == ["grassland"]


@pytest.mark.parametrize("crop", GROWING, ids=lambda crop: crop.id)
def test_growing_crop_has_every_parameter_with_provenance(crop: CatalogCrop):
    values = crop.growth.sourced_values()
    required = {
        "season",
        "critical_period",
        "stages",
        "kc_ini",
        "kc_mid",
        "kc_end",
        "root_depth_m",
        "depletion_fraction",
    }
    assert required <= set(values) <= required | {"yield_response_ky", "drought_monitoring_group"}
    for name, value in values.items():
        # Every catalogue value names its document; a provisional one also says why.
        assert (value.source or "").strip(), name
        assert value.provisional is None or value.provisional.strip(), name
    assert crop.name[0].isupper() and crop.name_genitive[0].islower()
    # An entry is conditional exactly when some of its values are provisional.
    assert crop.conditional == any(value.is_provisional for value in values.values())


@pytest.mark.parametrize("crop", GROWING, ids=lambda crop: crop.id)
def test_dates_of_growing_crop_are_coherent(crop: CatalogCrop):
    # Re-validation runs the same consistency rules the model enforces on creation.
    CropGrowth.model_validate(crop.growth.model_dump())
    season = crops.last_season(crop, date(2023, 12, 31))
    critical = crops.last_critical_period(crop, season.end)
    assert season.start <= critical.start <= critical.end <= season.end
    assert season.days < 366
    stages = crop.growth.stages.value
    if stages.maturity is not None:
        maturity = date(season.end.year, stages.maturity.month, stages.maturity.day)
        late = date(season.end.year, stages.late_start.month, stages.late_start.day)
        assert late < maturity <= season.end


@pytest.mark.parametrize("crop", ALL_CROPS, ids=lambda crop: crop.id)
def test_kc_curve_has_no_jumps_inside_the_season(crop: CatalogCrop):
    """The curve changes gradually; the only step is the harvest (back to bare soil)."""
    day, end = date(2019, 1, 1), date(2024, 12, 31)
    previous = crops.kc(crop, day)
    low = min(0.3, crop.growth.kc_end.value) if crop.growth else 0.3
    while day < end:
        day += timedelta(days=1)
        current = crops.kc(crop, day)
        assert low <= current <= 1.2
        after_harvest = crops.in_season(crop, day - timedelta(days=1)) and not crops.in_season(
            crop, day
        )
        if not after_harvest:
            # Steepest change of the list: pea ripens from Kc mid to Kc end in 7 days.
            assert abs(current - previous) <= 0.125, day
        previous = current


@pytest.mark.parametrize("module", DATA_MODULES, ids=lambda module: module.__name__)
def test_every_conditional_entry_is_marked_in_its_data_file(module):
    conditional = [crop for crop in module.CROPS if crop.conditional]
    assert inspect.getsource(module).count("# PROVISIONAL:") == len(conditional)


def test_bare_soil_coefficient_is_the_only_working_value_outside_conditional_entries():
    assert crop_data.BARE_SOIL_KC.is_provisional and crop_data.BARE_SOIL_KC.value == 0.3
    assert inspect.getsource(crop_data).count("# PROVISIONAL:") == 1
    for crop in GROWING:
        if not crop.conditional:
            assert not any(value.is_provisional for value in crop.growth.sourced_values().values())


def test_winter_wheat_values_and_their_sources():
    growth = crops.get_crop("winter_wheat").growth
    assert (growth.kc_ini.value, growth.kc_mid.value, growth.kc_end.value) == (0.4, 1.15, 0.25)
    assert growth.root_depth_m.value == (1.5, 1.8)
    assert growth.depletion_fraction.value == 0.55
    assert growth.yield_response_ky.value == 1.05
    assert growth.drought_monitoring_group.value == "zboża ozime"
    for value in (growth.kc_ini, growth.kc_mid, growth.kc_end):
        assert value.source.startswith("FAO-56 tab. 12: Winter Wheat")
    for value in (growth.root_depth_m, growth.depletion_fraction):
        assert value.source == "FAO-56 tab. 22: Winter Wheat"
    assert growth.yield_response_ky.source.startswith("FAO-56 tab. 24")
    assert growth.season.source.startswith("COBORU") and growth.stages.source == growth.season.source
    assert growth.critical_period.source.startswith("CDR 2025")
    assert not any(value.is_provisional for value in growth.sourced_values().values())


@pytest.mark.parametrize(
    ("crop_id", "provisional"),
    [
        ("winter_rye", {"kc_ini", "kc_end", "root_depth_m", "depletion_fraction"}),
        ("winter_rapeseed", {"stages", "kc_mid"}),
        ("grassland", {"season", "stages"}),
        ("tomato", {"stages", "critical_period", "kc_end"}),
        ("onion", {"season", "stages", "critical_period"}),
    ],
)
def test_conditional_entries_say_which_values_are_provisional(crop_id: str, provisional: set):
    crop = crops.get_crop(crop_id)
    values = crop.growth.sourced_values()
    assert {name for name, value in values.items() if value.is_provisional} == provisional
    assert crop.note


def test_values_missing_in_the_source_are_absent_not_invented():
    assert crops.get_crop("winter_rye").growth.yield_response_ky is None
    assert crops.get_crop("grassland").growth.drought_monitoring_group is None
    assert crops.get_crop("maize").growth.yield_response_ky.value == 1.25
    assert crops.get_crop("maize_silage").growth.stages.value.maturity is None


def test_bare_field_has_no_season_and_no_critical_period():
    bare = crops.get_crop("bare_field")
    assert bare.growth is None and bare.season is None and bare.critical_period is None
    day = date(2023, 6, 20)
    assert not crops.in_season(bare, day)
    assert crops.season_on(bare, day) is None and crops.last_season(bare, day) is None
    assert crops.critical_period_on(bare, day) is None
    assert crops.last_critical_period(bare, day) is None


def test_unknown_crop():
    assert not crops.has_crop("soybean")
    with pytest.raises(crops.UnknownCropError):
        crops.get_crop("soybean")
    with pytest.raises(KeyError):
        crops.get_crop("")


def test_catalogue_is_immutable():
    wheat = crops.get_crop("winter_wheat")
    with pytest.raises(ValidationError):
        wheat.name = "Inna"
    with pytest.raises(ValidationError):
        wheat.growth.kc_mid.value = 2.0


def test_value_without_source_or_provisional_reason_is_rejected():
    with pytest.raises(ValidationError, match="source or a provisional reason"):
        Sourced[float](value=1.0)
    with pytest.raises(ValidationError, match="source or a provisional reason"):
        Sourced[float](value=1.0, source="  ")


def test_contract_shape():
    listed = crops.contract_crops()
    assert [crop.id for crop in listed] == [crop.id for crop in ALL_CROPS]
    for crop in listed:
        assert Crop.model_validate(crop.model_dump()) == crop
    wheat = crops.to_contract(crops.get_crop("winter_wheat")).model_dump()
    assert wheat == {
        "id": "winter_wheat",
        "name": "Pszenica ozima",
        "name_genitive": "pszenicy ozimej",
        "tile": True,
        "season": {"start": {"month": 10, "day": 5}, "end": {"month": 8, "day": 1}},
        "critical_period": {"start": {"month": 5, "day": 11}, "end": {"month": 7, "day": 10}},
    }
    bare = crops.to_contract(crops.get_crop("bare_field"))
    assert bare.season is None and bare.critical_period is None


def test_placeholder_examples_and_simulation_name_catalogue_crops():
    placeholder = mock_data.catalog()
    for example in placeholder.examples:
        assert crops.has_crop(example.crop_id)
    for other in [placeholder.simulation.current, *placeholder.simulation.others]:
        assert crops.get_crop(other.crop_id).name == other.name
