"""Year-by-year comparison of the current crop with one other crop."""

from datetime import date

from app.engine.simulation import compare_years, simulate
from tests.engine_helpers import source_data
from tests.simulation_helpers import made_crop, weather_with_dry_years

DRY = {2015, 2018, 2019, 2023}
EARLY = made_crop("early")  # critical period 15 May - 30 June
LATE = made_crop("late", shape="spring")  # critical period 1 July - 20 August


def compared(analysis_date: date, first: date = date(2012, 9, 1), **options):
    data = source_data(weather_with_dry_years(first, date(2023, 12, 31), DRY, **options))
    simulation = simulate(data, EARLY, analysis_date, [LATE])
    return simulation, compare_years(simulation.current, simulation.other("late"))


def test_years_of_both_crops_side_by_side():
    simulation, years = compared(date(2023, 9, 30))
    assert [year.year for year in years] == list(range(2014, 2024))
    for year in years:
        assert year.current_deficit == year.other_deficit == (year.year in DRY)
        assert not year.partial
    # The list agrees with the numbers shown for both crops.
    assert sum(year.current_deficit for year in years) == simulation.current.verdict.deficit_years
    assert len(years) == simulation.current.verdict.total_years == 10


def test_year_is_partial_when_either_critical_period_is_still_running():
    # 10 July 2023: the early period is over, the late one has run for 10 days.
    _, years = compared(date(2023, 7, 10))
    assert [year.partial for year in years] == [False] * 9 + [True]
    assert years[-1].year == 2023 and years[-1].other_deficit

    # 20 June 2023: the early period is running; the late one has not begun, so
    # its window is 2013-2022 and the year 2023 cannot be compared.
    simulation, years = compared(date(2023, 6, 20))
    assert [year.year for year in years] == list(range(2014, 2023))
    assert not any(year.partial for year in years)
    assert simulation.current.verdict.years[-1].partial
    assert simulation.current.verdict.total_years == 10


def test_year_without_an_assessment_of_one_crop_is_left_out():
    # No weather from 1 May to 30 June 2018: the early crop has no assessed
    # critical period in 2018, the late crop has.
    gap = (date(2018, 5, 1), date(2018, 6, 30))
    simulation, years = compared(date(2023, 9, 30), missing=gap)
    assert simulation.current.verdict.total_years == 9
    assert simulation.other("late").verdict.total_years == 10
    assert [year.year for year in years] == [2014, 2015, 2016, 2017, 2019, 2020, 2021, 2022, 2023]

    # The same when the weather begins too late for the oldest year of both.
    _, years = compared(date(2023, 9, 30), first=date(2015, 1, 1))
    assert [year.year for year in years] == list(range(2015, 2024))


def test_wet_years_have_no_deficit_and_a_crop_not_simulated_is_absent():
    wet_enough = source_data(
        weather_with_dry_years(date(2012, 9, 1), date(2023, 12, 31), set())
    )
    simulation = simulate(wet_enough, EARLY, date(2023, 9, 30), [LATE])
    years = compare_years(simulation.current, simulation.other("late"))
    assert not any(year.current_deficit or year.other_deficit for year in years)
    assert simulation.other("missing") is None
