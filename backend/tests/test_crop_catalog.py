"""Crop catalogue: completeness, provenance of every value, lookup, contract shape."""

import inspect
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.catalog import crop_data, crops
from app.catalog.crop_model import CatalogCrop, CropGrowth, Sourced
from app.contracts.catalog import Crop
from app.mock import data as mock_data

ALL_CROPS = crops.list_crops()
GROWING = [crop for crop in ALL_CROPS if crop.growth is not None]


def provenance_values() -> list[Sourced]:
    values = [crop_data.BARE_SOIL_KC]
    for crop in GROWING:
        values += crop.growth.sourced_values().values()
    return values


def test_list_holds_winter_wheat_and_exactly_one_bare_field():
    assert crops.has_crop("winter_wheat")
    assert [crop.id for crop in ALL_CROPS if crop.is_bare_field] == ["bare_field"]
    assert crops.get_crop("bare_field").name == "Pole bez uprawy"


def test_identifiers_and_names_are_unique():
    assert len({crop.id for crop in ALL_CROPS}) == len(ALL_CROPS)
    assert len({crop.name for crop in ALL_CROPS}) == len(ALL_CROPS)


@pytest.mark.parametrize("crop", GROWING, ids=lambda crop: crop.id)
def test_growing_crop_has_every_parameter_with_provenance(crop: CatalogCrop):
    values = crop.growth.sourced_values()
    assert set(values) == {
        "season",
        "critical_period",
        "stages",
        "kc_ini",
        "kc_mid",
        "kc_end",
        "root_depth_m",
        "depletion_fraction",
    }
    for name, value in values.items():
        assert value.source or value.provisional, name
    assert crop.name[0].isupper() and crop.name_genitive[0].islower()


@pytest.mark.parametrize("crop", GROWING, ids=lambda crop: crop.id)
def test_dates_of_growing_crop_are_coherent(crop: CatalogCrop):
    # Re-validation runs the same consistency rules the model enforces on creation.
    CropGrowth.model_validate(crop.growth.model_dump())
    season = crops.last_season(crop, date(2023, 12, 31))
    critical = crops.last_critical_period(crop, season.end)
    assert season.start <= critical.start <= critical.end <= season.end
    assert season.days < 366


@pytest.mark.parametrize("crop", ALL_CROPS, ids=lambda crop: crop.id)
def test_kc_curve_has_no_jumps_over_the_years(crop: CatalogCrop):
    day, end = date(2019, 1, 1), date(2024, 12, 31)
    previous = crops.kc(crop, day)
    while day < end:
        day += timedelta(days=1)
        current = crops.kc(crop, day)
        assert 0 < current <= 2
        assert abs(current - previous) <= 0.05, day
        previous = current


def test_every_provisional_value_is_marked_in_the_data_file():
    provisional = [value for value in provenance_values() if value.is_provisional]
    marks = inspect.getsource(crop_data).count("# PROVISIONAL:")
    assert marks == len(provisional)


def test_winter_wheat_values_and_their_sources():
    growth = crops.get_crop("winter_wheat").growth
    assert (growth.kc_ini.value, growth.kc_mid.value, growth.kc_end.value) == (0.4, 1.15, 0.3)
    assert growth.root_depth_m.value == (1.5, 1.8)
    assert growth.depletion_fraction.value == 0.55
    for value in (growth.kc_ini, growth.kc_mid, growth.kc_end):
        assert "FAO Irrigation and Drainage Paper 56, Table 12" in value.source
    for value in (growth.root_depth_m, growth.depletion_fraction):
        assert "FAO Irrigation and Drainage Paper 56, Table 22" in value.source
    sourced_only = {
        name for name, value in growth.sourced_values().items() if not value.is_provisional
    }
    assert sourced_only == {"kc_mid", "root_depth_m", "depletion_fraction"}
    assert crop_data.BARE_SOIL_KC.is_provisional


def test_bare_field_has_no_season_and_no_critical_period():
    bare = crops.get_crop("bare_field")
    assert bare.growth is None and bare.season is None and bare.critical_period is None
    day = date(2023, 6, 20)
    assert not crops.in_season(bare, day)
    assert crops.season_on(bare, day) is None and crops.last_season(bare, day) is None
    assert crops.critical_period_on(bare, day) is None
    assert crops.last_critical_period(bare, day) is None


def test_unknown_crop():
    assert not crops.has_crop("oats")
    with pytest.raises(crops.UnknownCropError):
        crops.get_crop("oats")
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
        "season": {"start": {"month": 9, "day": 25}, "end": {"month": 7, "day": 31}},
        "critical_period": {"start": {"month": 5, "day": 15}, "end": {"month": 6, "day": 30}},
    }
    bare = crops.to_contract(crops.get_crop("bare_field"))
    assert bare.season is None and bare.critical_period is None


def test_catalogue_identifiers_are_known_to_the_placeholder_routes():
    placeholder = {crop.id for crop in mock_data.catalog().crops}
    assert {crop.id for crop in ALL_CROPS} <= placeholder
