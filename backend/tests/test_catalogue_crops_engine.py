"""Every catalogue crop through the engine: season states, dormancy, both verdicts, a Report."""

from datetime import date

import pytest

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import critical_period_on, get_crop, list_crops
from app.contracts.report import Report
from app.engine.assessment import assess_water
from app.engine.causes import deficit_causes
from app.engine.season import critical_period_date, dormancy_period, season_status
from tests.analysis_helpers import start, wait_finished
from tests.engine_helpers import recorded_soil, recorded_weather, source_data
from tests.summary_helpers import build

GROWING = [crop for crop in list_crops() if crop.growth is not None]
WINTER = {"winter_wheat", "winter_rye", "winter_triticale", "winter_barley", "winter_rapeseed"}
ANALYSIS_DATE = date(2023, 6, 20)


@pytest.fixture(scope="module")
def recorded():
    return source_data(recorded_weather(), recorded_soil())


def test_only_winter_crops_have_a_dormancy():
    assert {crop.id for crop in GROWING if dormancy_period(crop) is not None} == WINTER


@pytest.mark.parametrize(
    ("crop_id", "day", "state"),
    [
        ("winter_wheat", date(2023, 10, 4), "out_of_season"),
        ("winter_wheat", date(2023, 10, 5), "in_season"),  # sowing, before emergence
        ("winter_wheat", date(2023, 10, 19), "dormant"),
        ("winter_wheat", date(2024, 3, 8), "dormant"),
        ("winter_wheat", date(2024, 3, 9), "in_season"),
        ("winter_wheat", date(2024, 8, 1), "in_season"),
        ("winter_wheat", date(2024, 8, 2), "out_of_season"),
        ("winter_rapeseed", date(2023, 8, 30), "in_season"),
        ("winter_rapeseed", date(2023, 12, 24), "dormant"),
        ("winter_rapeseed", date(2024, 3, 10), "in_season"),
        ("winter_rapeseed", date(2024, 7, 21), "out_of_season"),
        ("maize", date(2023, 4, 27), "out_of_season"),
        ("maize", date(2023, 5, 20), "in_season"),  # between emergence and development
        ("maize", date(2023, 10, 18), "in_season"),
        ("maize", date(2023, 12, 24), "out_of_season"),
        ("spring_barley", date(2023, 4, 14), "in_season"),
        ("potato", date(2023, 9, 25), "out_of_season"),
        ("grassland", date(2023, 1, 15), "out_of_season"),
        ("grassland", date(2023, 7, 1), "in_season"),
        ("cucumber", date(2023, 5, 22), "out_of_season"),
        ("cucumber", date(2023, 8, 15), "in_season"),
        ("bare_field", date(2023, 6, 20), "no_crop"),
    ],
)
def test_state_of_a_date_for_catalogue_crops(crop_id: str, day: date, state: str):
    assert season_status(get_crop(crop_id), day).state == state


@pytest.mark.parametrize("crop", GROWING, ids=lambda crop: crop.id)
def test_way_to_the_critical_period_is_never_later_than_the_date(crop: CatalogCrop):
    for day in (date(2023, 1, 15), date(2023, 6, 20), date(2023, 8, 31), date(2023, 11, 15)):
        target = critical_period_date(crop, day)
        assert target <= day
        assert critical_period_on(crop, target) is not None


@pytest.mark.parametrize("crop", GROWING, ids=lambda crop: crop.id)
def test_every_crop_gets_both_verdicts_and_causes(crop: CatalogCrop, recorded):
    result = assess_water(recorded, crop, ANALYSIS_DATE)
    assert result.current_status.deficit_level in range(4)
    verdict = result.multiyear_susceptibility
    assert verdict.total_years == 10 and 0 <= verdict.deficit_years <= 10
    assert verdict.deficit_level in range(4)
    # The root zone is the shallower of the crop's roots (the deep end of the tabulated
    # range, as for rainfed crops) and the soil profile.
    deep_m = crop.growth.root_depth_m.value[1]
    assert result.root_zone.depth_cm == pytest.approx(min(deep_m * 100, 100.0))
    again = assess_water(recorded, crop, ANALYSIS_DATE)
    assert again.multiyear_susceptibility == verdict
    outcome = deficit_causes(result, crop, None)
    assert outcome.status == "determined"
    demand = {cause.id: cause for cause in outcome.results}["crop_demand"]
    assert demand.value == crop.growth.kc_mid.value
    # Working threshold of the cause: Kc mid above 1.0. Only field cucumber is not above it.
    assert (demand.state == "found") == (crop.id != "cucumber")


def test_numbers_of_winter_wheat_and_grain_maize_on_the_recorded_parcel(recorded):
    """Computed with the catalogue values on recorded weather and soil (TAW 186 mm)."""
    wheat = assess_water(recorded, get_crop("winter_wheat"), ANALYSIS_DATE)
    assert wheat.current_status.deficit_level == 3
    assert wheat.current_status.details()["stress_coefficient"] == 0.32
    years = wheat.multiyear_susceptibility.years
    assert [year.year for year in years] == list(range(2014, 2024))
    assert [year.stress_days for year in years] == [29, 46, 47, 13, 49, 36, 31, 26, 52, 22]
    assert wheat.multiyear_susceptibility.deficit_years == 10 and years[-1].partial
    maize = assess_water(recorded, get_crop("maize"), ANALYSIS_DATE)
    # On 20 June the critical period of maize (July-August) of 2023 has not begun.
    assert maize.current_status.deficit_level == 0
    years = maize.multiyear_susceptibility.years
    assert [year.year for year in years] == list(range(2013, 2023))
    assert [year.stress_days for year in years] == [37, 52, 46, 18, 0, 30, 60, 24, 38, 50]
    in_july = assess_water(recorded, get_crop("maize"), date(2023, 7, 20))
    assert in_july.current_status.deficit_level == 2
    assert in_july.multiyear_susceptibility.years[-1].stress_days == 13


@pytest.mark.parametrize("crop", GROWING, ids=lambda crop: crop.id)
def test_report_is_built_for_every_crop_in_and_out_of_season(crop: CatalogCrop):
    for day in (ANALYSIS_DATE, date(2023, 11, 15)):
        report = build(crop.id, day)
        assert Report.model_validate(report.model_dump()) == report
        assert report.meta.crop.id == crop.id and crop.name_genitive
        status = season_status(crop, day)
        assert report.season.in_season == status.in_season
        if not status.in_season:
            assert crop.name_genitive in report.season.note
            assert report.irrigation.justified is not True


def test_history_with_catalogue_crops_gives_the_course_of_each_year(client):
    source_id = start(client)
    assert wait_finished(client, source_id)["state"] == "done"
    years = {"2018": "maize", "2019": "potato", "2020": "winter_rapeseed", "2021": "bare_field"}
    derived = client.post(
        f"/api/reports/{source_id}/derive", json={"crop_history": {"years": years}}
    )
    assert derived.status_code == 201, derived.text
    report = Report.model_validate(
        client.get(f"/api/reports/{derived.json()['report_id']}").json()
    )
    course = {year.year: year for year in report.historical_course.years}
    assert {year: entry.crop.id for year, entry in course.items()} == {
        2014: "winter_wheat", 2015: "winter_wheat", 2016: "winter_wheat", 2017: "winter_wheat",
        2018: "maize", 2019: "potato", 2020: "winter_rapeseed", 2021: "bare_field",
        2022: "winter_wheat", 2023: "winter_wheat",
    }  # fmt: skip
    assert course[2018].crop.name == "Kukurydza na ziarno"
    # Same years as the simulation of each crop on the same recorded data.
    assert (course[2018].deficit, course[2019].deficit, course[2020].deficit) == (True, True, True)
    source = Report.model_validate(client.get(f"/api/reports/{source_id}").json())
    # The history does not change the multi-year susceptibility.
    assert report.multiyear_susceptibility.years == source.multiyear_susceptibility.years
    assert report.multiyear_susceptibility.deficit_years == 10
