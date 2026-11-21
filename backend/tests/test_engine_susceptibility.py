"""Multi-year susceptibility: window, deficit years, partial year, level thresholds.

The critical period of winter wheat in the catalogue is 15 May - 30 June
(47 days). Balances are built directly from chosen stress days.
"""

from datetime import date

import pytest

from app.contracts.verdicts import MultiyearYear
from app.engine.params import EngineParams
from app.engine.susceptibility import (
    multiyear_susceptibility,
    susceptibility_level,
    window_periods,
)
from tests.engine_helpers import BARE_FIELD, WHEAT, balance_with_stress, day_range

SERIES_START = date(2012, 9, 3)


def verdict_for(stressed, analysis_date=date(2023, 6, 20), first=SERIES_START, **changes):
    balance = balance_with_stress(first, analysis_date, stressed)
    return multiyear_susceptibility(balance, WHEAT, EngineParams(**changes))


def stress_in_years(days_by_year: dict[int, int]) -> set[date]:
    """`count` stress days from 15 May of each given year."""
    stressed: set[date] = set()
    for year, count in days_by_year.items():
        stressed |= day_range(date(year, 5, 15), count)
    return stressed


@pytest.mark.parametrize(
    ("deficit_years", "level"),
    [(0, 0), (2, 0), (3, 1), (4, 1), (5, 2), (7, 2), (8, 3), (10, 3)],
)
def test_level_thresholds_are_inclusive(deficit_years, level):
    assert susceptibility_level(deficit_years) == level


def test_level_thresholds_come_from_parameters():
    params = EngineParams(susceptibility_level_min_years=(1, 2, 3))
    assert [susceptibility_level(n, params) for n in range(5)] == [0, 1, 2, 3, 3]


def test_window_is_the_last_ten_critical_periods_started_by_the_analysis_date():
    periods = window_periods(WHEAT, date(2023, 6, 20))
    assert [period.start for period in periods] == [date(y, 5, 15) for y in range(2014, 2024)]
    assert all(period.end == date(period.start.year, 6, 30) for period in periods)


def test_window_before_the_critical_period_ends_with_the_previous_year():
    periods = window_periods(WHEAT, date(2023, 5, 14))
    assert [period.start.year for period in periods] == list(range(2013, 2023))
    assert window_periods(WHEAT, date(2023, 5, 15))[-1].start.year == 2023


def test_window_length_is_a_parameter():
    assert len(window_periods(WHEAT, date(2023, 6, 20), EngineParams(window_years=4))) == 4


def test_year_needs_the_configured_number_of_stress_days():
    verdict = verdict_for(stress_in_years({2015: 9, 2016: 10, 2017: 11}))
    by_year = {year.year: year for year in verdict.years}
    assert (by_year[2015].stress_days, by_year[2015].deficit) == (9, False)
    assert (by_year[2016].stress_days, by_year[2016].deficit) == (10, True)
    assert (by_year[2017].stress_days, by_year[2017].deficit) == (11, True)
    assert verdict.deficit_years == 2
    assert verdict.total_years == 10
    assert (verdict.deficit_level, verdict.label) == (0, "w normie")


def test_deficit_year_threshold_comes_from_parameters():
    verdict = verdict_for(stress_in_years({2015: 9, 2016: 10}), deficit_year_min_stress_days=5)
    assert verdict.deficit_years == 2


def test_stress_outside_the_critical_period_does_not_count():
    stressed = day_range(date(2020, 4, 1), 44) | day_range(date(2020, 7, 1), 60)
    verdict = verdict_for(stressed)
    assert all(year.stress_days == 0 for year in verdict.years)
    assert verdict.deficit_years == 0


def test_critical_period_boundaries_are_inclusive():
    stressed = {date(2020, 5, 14), date(2020, 5, 15), date(2020, 6, 30), date(2020, 7, 1)}
    year = next(y for y in verdict_for(stressed).years if y.year == 2020)
    assert year.stress_days == 2


def test_year_of_the_analysis_date_is_counted_only_up_to_that_date():
    verdict = verdict_for(stress_in_years({2023: 47}))
    last = verdict.years[-1]
    assert last.year == 2023 and last.partial
    # 15 May - 20 June.
    assert last.critical_period_days == 37
    assert last.stress_days == 37
    assert last.deficit
    assert [year.partial for year in verdict.years[:-1]] == [False] * 9
    assert all(year.critical_period_days == 47 for year in verdict.years[:-1])


def test_partial_year_below_the_threshold_is_not_a_deficit_year_yet():
    verdict = verdict_for(stress_in_years({2023: 47}), analysis_date=date(2023, 5, 23))
    last = verdict.years[-1]
    assert (last.critical_period_days, last.stress_days, last.deficit) == (9, 9, False)
    assert last.partial


def test_last_day_of_the_critical_period_closes_the_year():
    verdict = verdict_for(set(), analysis_date=date(2023, 6, 30))
    assert not verdict.years[-1].partial
    assert verdict.years[-1].critical_period_days == 47


def test_severe_level_when_most_years_lack_water():
    verdict = verdict_for(stress_in_years({year: 20 for year in range(2014, 2022)}))
    assert verdict.deficit_years == 8
    assert (verdict.deficit_level, verdict.label) == (3, "silny niedobór")


def test_years_without_weather_are_listed_but_not_counted():
    stressed = stress_in_years({2019: 20, 2021: 20, 2022: 20})
    verdict = verdict_for(stressed, first=date(2019, 1, 1))
    assert [year.assessed for year in verdict.years] == [False] * 5 + [True] * 5
    assert verdict.total_years == 5
    assert verdict.deficit_years == 3
    assert verdict.deficit_level == 1
    assert verdict.years[0].precipitation_mm is None
    assert verdict.years[0].values()["precipitation_apr_jul_mm"] is None


def test_series_starting_inside_a_critical_period_shows_the_missing_days():
    verdict = verdict_for(set(), first=date(2019, 6, 1))
    year = next(y for y in verdict.years if y.year == 2019)
    assert year.assessed
    assert (year.critical_period_days, year.days_with_weather) == (47, 30)


def test_no_weather_at_all_means_not_assessed():
    balance = balance_with_stress(date(2023, 1, 1), date(2022, 12, 31), set(), date(2023, 6, 20))
    verdict = multiyear_susceptibility(balance, WHEAT)
    assert not verdict.assessed
    assert verdict.not_assessed_reason == "no_weather"
    assert verdict.total_years == 0 and len(verdict.years) == 10


def test_bare_field_has_no_critical_period_and_is_not_assessed():
    balance = balance_with_stress(SERIES_START, date(2023, 6, 20), set())
    verdict = multiyear_susceptibility(balance, BARE_FIELD)
    assert not verdict.assessed
    assert verdict.not_assessed_reason == "no_crop"
    assert verdict.years == () and verdict.total_years == 0


def test_yearly_sums_cover_the_configured_months_up_to_the_analysis_date():
    # Every day has 1 mm of rain and 3 mm of ET0.
    verdict = verdict_for(set())
    full, partial = verdict.years[0], verdict.years[-1]
    # April - July has 122 days; 1 April - 20 June has 81.
    assert (full.precipitation_mm, full.climatic_water_balance_mm) == (122.0, -244.0)
    assert (partial.precipitation_mm, partial.climatic_water_balance_mm) == (81.0, -162.0)
    may_only = verdict_for(set(), climatic_balance_months=(5, 5)).years[0]
    assert may_only.precipitation_mm == 31.0
    assert "precipitation_may_may_mm" in may_only.values()


def test_year_values_fit_the_report_contract():
    year = verdict_for(stress_in_years({2023: 20})).years[-1]
    values = year.values()
    assert values == {
        "stress_days": 20,
        "critical_period_days": 37,
        "days_with_weather": 37,
        "climatic_water_balance_apr_jul_mm": -162,
        "precipitation_apr_jul_mm": 81,
    }
    entry = MultiyearYear(year=year.year, deficit=year.deficit, partial=year.partial, values=values)
    assert entry.deficit and entry.partial
