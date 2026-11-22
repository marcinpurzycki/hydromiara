"""State of the analysis date for a crop and the date of the critical-period analysis."""

from datetime import date, timedelta

import pytest

from app.catalog.periods import DateRange
from app.engine.season import (
    critical_period_date,
    critical_period_for,
    dormancy_on,
    dormancy_period,
    finished_season,
    season_status,
)
from tests.engine_helpers import BARE_FIELD, WHEAT
from tests.season_helpers import SPRING

SEASON_23 = DateRange(date(2022, 9, 25), date(2023, 7, 31))
SEASON_24 = DateRange(date(2023, 9, 25), date(2024, 7, 31))
DORMANCY_23 = DateRange(date(2022, 10, 27), date(2023, 3, 15))


@pytest.mark.parametrize(
    ("day", "state", "last"),
    [
        (date(2022, 9, 24), "out_of_season", DateRange(date(2021, 9, 25), date(2022, 7, 31))),
        (date(2022, 9, 25), "in_season", SEASON_23),  # sowing
        (date(2022, 10, 26), "in_season", SEASON_23),  # last day of emergence
        (date(2022, 10, 27), "dormant", SEASON_23),  # emergence ends
        (date(2022, 11, 15), "dormant", SEASON_23),  # autumn after emergence
        (date(2022, 12, 31), "dormant", SEASON_23),
        (date(2023, 1, 1), "dormant", SEASON_23),  # winter
        (date(2023, 3, 15), "dormant", SEASON_23),  # last day of dormancy
        (date(2023, 3, 16), "in_season", SEASON_23),  # spring growth starts
        (date(2023, 5, 15), "in_season", SEASON_23),  # critical period
        (date(2023, 6, 20), "in_season", SEASON_23),
        (date(2023, 7, 31), "in_season", SEASON_23),  # harvest
        (date(2023, 8, 1), "out_of_season", SEASON_23),  # day after harvest
        (date(2023, 9, 24), "out_of_season", SEASON_23),
        (date(2024, 2, 29), "dormant", SEASON_24),  # leap day
    ],
)
def test_winter_wheat_state(day, state, last):
    status = season_status(WHEAT, day)
    assert (status.state, status.last_season) == (state, last)
    assert status.in_season == (state != "out_of_season")
    assert status.store_assessed == (state != "in_season")
    assert (status.dormancy is not None) == (state == "dormant")


def test_dormancy_comes_from_the_stage_dates_of_the_crop():
    stages = WHEAT.growth.stages.value
    period = dormancy_period(WHEAT)
    assert (period.start, period.end) == (stages.establishment_end, stages.development_start)
    assert dormancy_on(WHEAT, date(2023, 1, 10)) == DORMANCY_23
    assert season_status(WHEAT, date(2023, 1, 10)).dormancy == DORMANCY_23
    assert dormancy_on(WHEAT, date(2024, 2, 29)) == DateRange(date(2023, 10, 27), date(2024, 3, 15))
    assert dormancy_on(WHEAT, date(2023, 3, 16)) is None
    # A spring crop has the same stage, but it does not run across the winter.
    assert dormancy_period(SPRING) is None and dormancy_period(BARE_FIELD) is None
    assert dormancy_on(SPRING, date(2023, 5, 15)) is None


def test_finished_season_is_the_latest_one_that_ended_before_the_day():
    before = DateRange(date(2021, 9, 25), date(2022, 7, 31))
    assert finished_season(WHEAT, date(2023, 7, 31)) == before  # harvest day: still running
    assert finished_season(WHEAT, date(2023, 8, 1)) == SEASON_23
    assert finished_season(WHEAT, date(2023, 11, 15)) == SEASON_23  # next season is running
    assert finished_season(BARE_FIELD, date(2023, 8, 1)) is None
    status = season_status(WHEAT, date(2023, 11, 15))
    assert (status.last_season, status.finished_season) == (SEASON_24, SEASON_23)


@pytest.mark.parametrize(
    ("day", "state", "last_start"),
    [
        (date(2023, 11, 15), "out_of_season", date(2023, 4, 20)),  # November
        (date(2023, 7, 15), "in_season", date(2023, 4, 20)),  # July
        (date(2024, 1, 20), "out_of_season", date(2023, 4, 20)),  # winter
        (date(2024, 2, 29), "out_of_season", date(2023, 4, 20)),
        (date(2023, 4, 19), "out_of_season", date(2022, 4, 20)),
        (date(2023, 4, 20), "in_season", date(2023, 4, 20)),
        (date(2023, 5, 15), "in_season", date(2023, 4, 20)),  # initial stage is not dormancy
        (date(2023, 10, 10), "in_season", date(2023, 4, 20)),
        (date(2023, 10, 11), "out_of_season", date(2023, 4, 20)),
    ],
)
def test_spring_crop_state(day, state, last_start):
    status = season_status(SPRING, day)
    assert (status.state, status.last_season.start) == (state, last_start)
    assert status.dormancy is None
    assert status.finished_season.end < day


def test_field_without_a_crop_has_no_season():
    status = season_status(BARE_FIELD, date(2023, 6, 20))
    assert status.state == "no_crop" and not status.in_season and not status.store_assessed
    assert status.last_season is status.finished_season is status.dormancy is None
    assert critical_period_date(BARE_FIELD, date(2023, 6, 20)) is None
    assert critical_period_for(BARE_FIELD, date(2023, 6, 20)) is None


# Winter wheat: critical period 15 May - 30 June, middle day 7 June.
@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2023, 3, 1), date(2022, 6, 7)),  # before the period of the year
        (date(2023, 5, 14), date(2022, 6, 7)),
        (date(2023, 5, 15), date(2022, 6, 7)),  # in the period, before its middle
        (date(2023, 6, 6), date(2022, 6, 7)),
        (date(2023, 6, 7), date(2023, 6, 7)),  # exactly the middle
        (date(2023, 6, 8), date(2023, 6, 7)),  # in the period, after its middle
        (date(2023, 6, 30), date(2023, 6, 7)),
        (date(2023, 7, 1), date(2023, 6, 7)),  # after the period
        (date(2023, 11, 15), date(2023, 6, 7)),
        (date(2024, 2, 29), date(2023, 6, 7)),
        (date(2024, 6, 7), date(2024, 6, 7)),
    ],
)
def test_winter_wheat_critical_period_date(day, expected):
    assert critical_period_date(WHEAT, day) == expected
    assert critical_period_for(WHEAT, day).midpoint == expected


# Spring crop: critical period 1 July - 20 August, middle day 26 July.
@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2023, 6, 30), date(2022, 7, 26)),
        (date(2023, 7, 15), date(2022, 7, 26)),
        (date(2023, 7, 25), date(2022, 7, 26)),
        (date(2023, 7, 26), date(2023, 7, 26)),
        (date(2023, 8, 20), date(2023, 7, 26)),
        (date(2023, 11, 15), date(2023, 7, 26)),
        (date(2024, 1, 20), date(2023, 7, 26)),
    ],
)
def test_spring_crop_critical_period_date(day, expected):
    assert critical_period_date(SPRING, day) == expected


@pytest.mark.parametrize("crop", [WHEAT, SPRING])
def test_critical_period_date_is_never_later_than_the_analysis_date(crop):
    day = date(2019, 1, 1)
    previous = None
    while day <= date(2024, 12, 31):
        found = critical_period_date(crop, day)
        assert found <= day
        assert day - found < timedelta(days=366)
        # Asking again from the found date changes nothing: it is a middle day.
        assert critical_period_date(crop, found) == found
        assert previous is None or found >= previous
        previous = found
        day += timedelta(days=1)
