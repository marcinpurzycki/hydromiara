"""Whole water assessment on recorded weather: trial numbers, no leak from the future,
determinism, missing soil, the field without a crop."""

import copy
import json
from datetime import date, timedelta

import pytest

from app.engine.assessment import assess_water
from app.engine.root_zone import RootZone
from tests.engine_helpers import (
    BARE_FIELD,
    FIXTURES,
    WHEAT,
    recorded_soil,
    recorded_weather,
    source_data,
    weather_day,
)

ANALYSIS_DATE = date(2023, 6, 20)
# The trial calculation started on 1 January 2013 with TAW 216 mm and p 0.55.
TRIAL_START = date(2013, 1, 1)
TRIAL_ZONE = RootZone(depth_cm=100.0, taw_mm=216.0, depletion_fraction=0.55)


@pytest.fixture(scope="module")
def weather():
    return recorded_weather()


@pytest.fixture(scope="module")
def trial():
    path = FIXTURES / "dry_run_result.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_status_matches_the_trial_calculation(weather, trial):
    days = [day for day in weather if day.date >= TRIAL_START]
    result = assess_water(source_data(days), WHEAT, ANALYSIS_DATE, zone=TRIAL_ZONE)
    details = result.current_status.details()
    now = trial["now"]
    assert result.current_status.deficit_level == now["level"] == 3
    assert result.current_status.label == "silny niedobór"
    assert details["depletion_mm"] == now["depletion_mm"]
    assert details["readily_available_water_mm"] == now["raw_mm"]
    assert details["total_available_water_mm"] == now["taw_mm"]
    assert details["depletion_pct"] == now["depletion_pct"]
    assert details["stress_coefficient"] == now["ks"]
    assert details["stress_run_days"] == now["stress_run_days"]
    assert details["precipitation_30d_mm"] == now["p30_mm"]
    assert details["et0_30d_mm"] == now["et0_30_mm"]


def test_multiyear_susceptibility_matches_the_trial_calculation(weather, trial):
    days = [day for day in weather if day.date >= TRIAL_START]
    verdict = assess_water(
        source_data(days), WHEAT, ANALYSIS_DATE, zone=TRIAL_ZONE
    ).multiyear_susceptibility
    assert verdict.deficit_years == trial["deficit_years"] == 9
    assert verdict.total_years == 10
    assert verdict.deficit_level == 3
    assert len(verdict.years) == len(trial["years"])
    for year, expected in zip(verdict.years, trial["years"]):
        values = year.values()
        assert year.year == expected["year"]
        assert year.partial == expected["partial"]
        assert year.deficit == expected["deficit"]
        assert values["critical_period_days"] == expected["crit_days"]
        assert values["climatic_water_balance_apr_jul_mm"] == expected["kbw_iv_vii_mm"]
        assert values["precipitation_apr_jul_mm"] == expected["p_iv_vii_mm"]
        # The trial ties the Kc curve to the day of the year, the catalogue to
        # calendar dates; in the leap year 2020 this moves one stress day.
        tolerance = 1 if year.year == 2020 else 0
        assert abs(year.stress_days - expected["stress_days"]) <= tolerance


def test_recorded_soil_and_warm_up_keep_the_verdicts(weather):
    result = assess_water(source_data(weather, recorded_soil()), WHEAT, ANALYSIS_DATE)
    assert result.root_zone.capacity_source == "iung_category"
    # Category III of the soil map: 186 mm per metre (27 mm less than the water
    # contents used before), which adds the tenth deficit year.
    assert result.root_zone.taw_mm == pytest.approx(186.0)
    assert result.balance.days[0].date == date(2012, 9, 3)
    assert result.balance.incomplete_days == 0 and result.balance.missing_dates == 0
    assert result.current_status.deficit_level == 3
    assert result.multiyear_susceptibility.deficit_years == 10
    assert [year.year for year in result.multiyear_susceptibility.years] == list(range(2014, 2024))


def test_days_after_the_analysis_date_do_not_change_the_result(weather):
    soil = recorded_soil()
    until_date = [day for day in weather if day.date <= ANALYSIS_DATE]
    assert len(until_date) < len(weather)
    base = assess_water(source_data(until_date, soil), WHEAT, ANALYSIS_DATE)

    with_future = assess_water(source_data(weather, soil), WHEAT, ANALYSIS_DATE)
    assert with_future == base

    flooded = [
        day if day.date <= ANALYSIS_DATE else weather_day(day.date, 500.0, 0.0) for day in weather
    ]
    assert assess_water(source_data(flooded, soil), WHEAT, ANALYSIS_DATE) == base

    parched = until_date + [
        weather_day(ANALYSIS_DATE + timedelta(days=offset), 0.0, 9.0) for offset in range(1, 400)
    ]
    assert assess_water(source_data(parched, soil), WHEAT, ANALYSIS_DATE) == base


def test_changing_a_day_up_to_the_analysis_date_does_change_the_result(weather):
    # Guards the test above: equality there is not an accident of comparison.
    soil = recorded_soil()
    until_date = [day for day in weather if day.date <= ANALYSIS_DATE]
    base = assess_water(source_data(until_date, soil), WHEAT, ANALYSIS_DATE)
    wet_today = until_date[:-1] + [weather_day(ANALYSIS_DATE, 500.0, 0.0)]
    changed = assess_water(source_data(wet_today, soil), WHEAT, ANALYSIS_DATE)
    assert changed != base
    assert changed.current_status.deficit_level == 0


def test_earlier_analysis_date_sees_only_its_own_past(weather):
    soil = recorded_soil()
    earlier = date(2019, 6, 15)
    full = assess_water(source_data(weather, soil), WHEAT, earlier)
    cut = [day for day in weather if day.date <= earlier]
    assert full == assess_water(source_data(cut, soil), WHEAT, earlier)
    years = full.multiyear_susceptibility.years
    assert [year.year for year in years] == list(range(2010, 2020))
    # The recorded series starts in September 2012: three years have no weather.
    assert [year.assessed for year in years] == [False] * 3 + [True] * 7
    assert years[-1].partial and years[-1].critical_period_days == 32
    assert full.current_status.state_date == earlier


def test_same_input_gives_the_same_result(weather):
    data = source_data(weather, recorded_soil())
    first = assess_water(data, WHEAT, ANALYSIS_DATE)
    second = assess_water(copy.deepcopy(data), WHEAT, ANALYSIS_DATE)
    assert first == second
    assert first.current_status.details() == second.current_status.details()
    assert repr(first) == repr(second)


def test_input_is_not_modified(weather):
    data = source_data(weather, recorded_soil())
    before = data.model_dump_json()
    assess_water(data, WHEAT, ANALYSIS_DATE)
    assert data.model_dump_json() == before


def test_missing_soil_is_assessed_with_the_flagged_fallback(weather):
    result = assess_water(source_data(weather, None), WHEAT, ANALYSIS_DATE)
    assert result.root_zone.capacity_source == "fallback"
    assert result.root_zone.taw_mm == pytest.approx(150.0)
    assert result.current_status.assessed
    assert result.multiyear_susceptibility.total_years == 10


def test_verdicts_are_two_separate_results(weather):
    # A wet analysis day turns the current status to normal; the past years stay.
    soil = recorded_soil()
    until_date = [day for day in weather if day.date <= ANALYSIS_DATE]
    wet_today = until_date[:-1] + [weather_day(ANALYSIS_DATE, 500.0, 0.0)]
    result = assess_water(source_data(wet_today, soil), WHEAT, ANALYSIS_DATE)
    assert result.current_status.deficit_level == 0
    assert result.multiyear_susceptibility.deficit_level == 3
    assert result.multiyear_susceptibility.deficit_years == 10


def test_bare_field_runs_the_balance_without_verdict_levels(weather):
    result = assess_water(source_data(weather, recorded_soil()), BARE_FIELD, ANALYSIS_DATE)
    assert result.crop_id == "bare_field"
    assert len(result.balance.days) == len([d for d in weather if d.date <= ANALYSIS_DATE])
    assert all(day.kc == pytest.approx(0.3) and day.ks == 1.0 for day in result.balance.days)
    assert not any(day.stressed for day in result.balance.days)
    assert result.current_status.not_assessed_reason == "no_crop"
    assert 0.0 <= result.current_status.depletion_mm <= result.root_zone.taw_mm
    assert result.multiyear_susceptibility.not_assessed_reason == "no_crop"


def test_another_crop_on_the_same_data_gives_its_own_result(weather):
    data = source_data(weather, recorded_soil())
    wheat = assess_water(data, WHEAT, ANALYSIS_DATE)
    bare = assess_water(data, BARE_FIELD, ANALYSIS_DATE)
    assert wheat.current_status.depletion_mm > bare.current_status.depletion_mm
    assert assess_water(data, WHEAT, ANALYSIS_DATE) == wheat
