"""Historical course: which years, which crop, the same measure as the susceptibility."""

from datetime import date

import pytest

from app.contracts.analyses import CropHistory
from app.engine.assessment import assess_water
from app.engine.balance import run_balance
from app.engine.history import historical_course, window_years, years_outside_window
from app.engine.root_zone import root_zone
from app.engine.susceptibility import assess_period
from tests.engine_helpers import BARE_FIELD, WHEAT, recorded_weather
from tests.history_helpers import JUNE, SAME, WINDOW, course_of, data, lookup, years
from tests.season_helpers import SPRING


def flags(course) -> dict[int, bool]:
    return {year.year: year.deficit for year in course.years}


def test_no_history_means_no_course():
    assert course_of(None)[0] is None
    # An empty form and "not the same" without any year say nothing either.
    assert course_of(CropHistory(years={}))[0] is None
    assert course_of(CropHistory(same_every_year=False))[0] is None


def test_field_without_a_crop_has_no_window_and_no_course():
    assert window_years(BARE_FIELD, JUNE) == ()
    assert course_of(SAME, crop=BARE_FIELD)[0] is None


def test_window_years_are_the_years_of_the_susceptibility():
    assert window_years(WHEAT, JUNE) == WINDOW
    # Before the critical period of the year begins the window ends a year earlier.
    assert window_years(WHEAT, date(2023, 3, 1)) == tuple(range(2013, 2023))
    course, assessment = course_of(SAME)
    assert tuple(year.year for year in course.years) == WINDOW
    assert WINDOW == tuple(year.year for year in assessment.multiyear_susceptibility.years)


def test_same_every_year_repeats_the_susceptibility_year_by_year():
    course, assessment = course_of(SAME)
    verdict = assessment.multiyear_susceptibility
    assert course.same_every_year and not any(year.given for year in course.years)
    assert flags(course) == {year.year: year.deficit for year in verdict.years}
    assert (course.deficit_years, course.assessed_years) == (9, 10)
    assert (verdict.deficit_years, verdict.total_years) == (9, 10)
    assert [year.stress_days for year in course.years] == [y.stress_days for y in verdict.years]
    assert course.years[-1].partial and not course.years[0].partial
    assert course.other_crop_years == ()


def test_full_history_with_one_crop_named_for_every_year():
    course, assessment = course_of(CropHistory(years=dict.fromkeys(WINDOW, "winter_wheat")))
    assert all(year.given and year.same_crop for year in course.years)
    assert not course.same_every_year
    assert flags(course) == flags(course_of(SAME)[0])


def test_years_not_named_take_the_crop_of_the_analysis():
    course, _ = course_of(years(y2016=SPRING.id, y2019="bare_field"))
    by_year = {year.year: year for year in course.years}
    assert [year for year, entry in by_year.items() if entry.given] == [2016, 2019]
    assert by_year[2016].crop is SPRING and by_year[2019].crop is BARE_FIELD
    assert all(by_year[year].crop is WHEAT for year in WINDOW if year not in (2016, 2019))
    assert course.other_crop_years == (2016, 2019)
    same = {year.year: year for year in course_of(SAME)[0].years}
    for year in WINDOW:
        if year not in (2016, 2019):
            assert by_year[year].deficit == same[year].deficit
            assert by_year[year].stress_days == same[year].stress_days


def test_year_of_the_field_without_a_crop_is_not_assessed():
    course, _ = course_of(years(y2015="bare_field", y2016="bare_field"))
    bare = [year for year in course.years if year.crop.is_bare_field]
    assert [year.year for year in bare] == [2015, 2016]
    for year in bare:
        assert not year.assessed and year.not_assessed == "no_crop"
        assert year.deficit is False and year.critical_period is None
    # Both years are deficit years of the wheat, so two fewer are counted.
    assert (course.deficit_years, course.assessed_years) == (7, 8)


def test_spring_crop_is_judged_in_its_own_critical_period():
    """Another critical period gives another result for the same year and weather."""
    day = date(2023, 3, 1)
    source = data()
    window = window_years(WHEAT, day)
    history = CropHistory(years=dict.fromkeys(window, SPRING.id))
    course, assessment = course_of(history, day=day, source=source)
    wheat = {year.year: year for year in assessment.multiyear_susceptibility.years}
    spring = {year.year: year for year in course.years}
    assert spring[2013].critical_period.start == date(2013, 7, 1)
    assert spring[2013].critical_period.end == date(2013, 8, 20)
    assert wheat[2013].deficit is False and spring[2013].deficit is True
    assert spring[2016].stress_days != wheat[2016].stress_days

    # The year is exactly what the susceptibility of the spring crop would say.
    zone = root_zone(source.soil, SPRING)
    balance = run_balance(source.weather.days, SPRING, zone, day)
    for year in course.years:
        expected = assess_period(balance, year.critical_period)
        assert (year.deficit, year.stress_days) == (expected.deficit, expected.stress_days)
    own = assess_water(source, SPRING, day).multiyear_susceptibility
    shared = {year.year: year.deficit for year in own.years if year.year in spring}
    assert shared and all(spring[year].deficit == deficit for year, deficit in shared.items())


def test_winter_crop_belongs_to_the_year_of_its_harvest():
    course, _ = course_of(SAME)
    period = course.years[0].critical_period
    # Sown in the autumn of 2013, the wheat of 2014 has its critical period in 2014.
    assert (period.start, period.end) == (date(2014, 5, 15), date(2014, 6, 30))


def test_crop_whose_critical_period_has_not_begun_is_not_assessed():
    course, _ = course_of(years(y2023=SPRING.id))
    last = course.years[-1]
    assert last.critical_period.start == date(2023, 7, 1)
    assert (last.not_assessed, last.deficit, last.stress_days) == ("not_started", False, 0)
    assert course.assessed_years == 9


def test_partial_year_counts_only_days_up_to_the_analysis_date():
    day = date(2023, 7, 20)
    course, _ = course_of(years(y2023=SPRING.id), day=day)
    last = course.years[-1]
    assert last.assessed and last.partial
    assert last.stress_days <= (day - date(2023, 7, 1)).days + 1


def test_year_without_weather_is_not_assessed():
    weather = [day for day in recorded_weather() if day.date.year != 2018]
    course, assessment = course_of(years(y2017=SPRING.id), source=data(weather=weather))
    by_year = {year.year: year for year in course.years}
    assert by_year[2018].not_assessed == "no_weather" and not by_year[2018].deficit
    assert assessment.multiyear_susceptibility.total_years == 9
    assert course.assessed_years == 9


def test_years_outside_the_window_are_reported_and_ignored():
    history = years(y2010="winter_wheat", y2019="bare_field", y2024="winter_wheat")
    assert years_outside_window(history, WHEAT, JUNE) == (2010, 2024)
    course, _ = course_of(history)
    assert tuple(year.year for year in course.years) == WINDOW
    assert course.other_crop_years == (2019,)
    # Only years outside the window: nothing was said about the window.
    assert course_of(years(y2010="bare_field"))[0] is None


def test_scenes_are_matched_by_year_and_never_taken_from_the_future():
    course, _ = course_of(years(y2021=SPRING.id))
    scenes = {year.year: year.scene for year in course.years}
    assert scenes[2020] is None  # the only scene of 2020 has no index
    assert scenes[2022].date == date(2022, 6, 14)  # the newest of the year
    assert scenes[2023].date == date(2023, 6, 9)  # 25 June is after the analysis date
    in_season = {year.year: year.scene_in_season for year in course.years}
    assert in_season[2022] is True and in_season[2023] is True
    assert in_season[2021] is True and in_season[2014] is None
    assert all(year.scene is None for year in course_of(SAME, source=data(satellite=False))[0].years)


def test_scene_outside_the_season_of_the_crop_of_that_year():
    # A scene of December 2021 shows the wheat sown for 2022, not the wheat
    # harvested in 2021: for the year 2021 it lies outside the season.
    source = data()
    late = source.satellite.scenes[0].model_copy(update={"date": date(2021, 12, 5)})
    source = source.model_copy(
        update={"satellite": source.satellite.model_copy(update={"scenes": [late]})}
    )
    course, _ = course_of(SAME, source=source)
    year = next(year for year in course.years if year.year == 2021)
    assert year.scene.date == date(2021, 12, 5) and year.scene_in_season is False


@pytest.mark.parametrize("history", [SAME, years(y2015="bare_field", y2018=SPRING.id)])
def test_course_is_repeatable_and_blind_to_later_days(history):
    first, _ = course_of(history)
    again, _ = course_of(history)
    assert first == again
    cut = [day for day in recorded_weather() if day.date <= JUNE]
    assert course_of(history, source=data(weather=cut))[0] == first


def test_susceptibility_does_not_depend_on_the_history():
    source = data()
    before = assess_water(source, WHEAT, JUNE)
    historical_course(source, before, WHEAT, years(y2015=SPRING.id), lookup=lookup)
    assert assess_water(source, WHEAT, JUNE) == before
