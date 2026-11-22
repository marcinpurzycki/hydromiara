"""Crop coefficient curve, seasons and critical periods on real calendar days."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.catalog import crops
from app.catalog.crop_model import CatalogCrop, CropGrowth, Sourced, StageDates
from app.catalog.periods import DateRange, crosses_new_year, cycle_offset
from app.contracts.catalog import MonthDay, YearlyPeriod

WHEAT = crops.get_crop("winter_wheat")
BARE = crops.get_crop("bare_field")
TEST = "made up for the test"


def md(month: int, day: int) -> MonthDay:
    return MonthDay(month=month, day=day)


def period(start: tuple[int, int], end: tuple[int, int]) -> YearlyPeriod:
    return YearlyPeriod(start=md(*start), end=md(*end))


def stages(
    establishment_end, development_start, mid_start, late_start, maturity=None
) -> StageDates:
    return StageDates(
        establishment_end=md(*establishment_end),
        development_start=md(*development_start),
        mid_start=md(*mid_start),
        late_start=md(*late_start),
        maturity=None if maturity is None else md(*maturity),
    )


def growth(**changes) -> CropGrowth:
    """Made-up spring crop: sown 1 April, harvested 31 August, no establishment ramp."""
    fields = {
        "season": Sourced[YearlyPeriod](value=period((4, 1), (8, 31)), provisional=TEST),
        "critical_period": Sourced[YearlyPeriod](
            value=period((6, 1), (6, 30)), provisional=TEST
        ),
        "stages": Sourced[StageDates](
            value=stages((4, 1), (5, 1), (5, 31), (7, 30)), provisional=TEST
        ),
        "kc_ini": Sourced[float](value=0.5, provisional=TEST),
        "kc_mid": Sourced[float](value=1.1, provisional=TEST),
        "kc_end": Sourced[float](value=0.7, provisional=TEST),
        "root_depth_m": Sourced[tuple[float, float]](value=(1.0, 1.5), provisional=TEST),
        "depletion_fraction": Sourced[float](value=0.5, provisional=TEST),
    }
    for name, value in changes.items():
        fields[name] = Sourced(value=value, provisional=TEST)
    return CropGrowth.model_validate({name: item.model_dump() for name, item in fields.items()})


def crop(**changes) -> CatalogCrop:
    return CatalogCrop(
        id="test_crop",
        name="Testowa",
        name_genitive="testowej",
        tile=False,
        growth=growth(**changes),
    )


SPRING = crop()


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2022, 10, 4), 0.3),  # day before sowing: bare soil
        (date(2022, 10, 5), 0.3),  # sowing
        (date(2022, 10, 12), 0.35),  # half of the establishment (14 days)
        (date(2022, 10, 19), 0.4),  # establishment ends
        (date(2022, 12, 31), 0.4),  # dormancy across the turn of the year
        (date(2023, 1, 1), 0.4),
        (date(2023, 3, 9), 0.4),  # development starts
        (date(2023, 4, 18), 0.775),  # half of the development (40 of 80 days)
        (date(2023, 5, 28), 1.15),  # mid-season starts
        (date(2023, 6, 1), 1.15),
        (date(2023, 6, 21), 1.15),  # late season starts
        (date(2023, 7, 6), 1.15 - 0.9 * 15 / 30),
        (date(2023, 7, 21), 0.25),  # maturity: the fall ends
        (date(2023, 7, 27), 0.25),  # between maturity and harvest
        (date(2023, 8, 1), 0.25),  # harvest
        (date(2023, 8, 2), 0.3),  # after harvest: bare soil
        (date(2023, 10, 4), 0.3),
    ],
)
def test_winter_wheat_kc_in_stages_and_on_their_boundaries(day: date, expected: float):
    assert crops.kc(WHEAT, day) == pytest.approx(expected)


def test_winter_wheat_kc_in_a_leap_year():
    assert crops.kc(WHEAT, date(2024, 2, 29)) == pytest.approx(0.4)
    assert crops.kc(WHEAT, date(2024, 4, 18)) == pytest.approx(0.775)
    assert crops.kc(WHEAT, date(2024, 8, 1)) == pytest.approx(0.25)


def test_interpolation_counts_real_days_across_29_february():
    early = crop(
        season=period((1, 10), (6, 30)),
        critical_period=period((4, 1), (4, 30)),
        stages=stages((1, 10), (2, 1), (3, 31), (5, 31)),
    )
    assert crops.kc(early, date(2023, 3, 1)) == pytest.approx(0.5 + 0.6 * 28 / 58)
    assert crops.kc(early, date(2024, 3, 1)) == pytest.approx(0.5 + 0.6 * 29 / 59)
    assert crops.kc(early, date(2024, 2, 29)) == pytest.approx(0.5 + 0.6 * 28 / 59)


def test_spring_crop_curve_without_establishment_ramp():
    assert crops.kc(SPRING, date(2023, 3, 31)) == pytest.approx(0.3)
    assert crops.kc(SPRING, date(2023, 4, 1)) == pytest.approx(0.5)
    assert crops.kc(SPRING, date(2023, 5, 16)) == pytest.approx(0.8)
    assert crops.kc(SPRING, date(2023, 7, 30)) == pytest.approx(1.1)
    assert crops.kc(SPRING, date(2023, 8, 15)) == pytest.approx(0.9)
    assert crops.kc(SPRING, date(2023, 8, 31)) == pytest.approx(0.7)
    assert crops.kc(SPRING, date(2023, 9, 1)) == pytest.approx(0.3)


def test_maturity_ends_the_fall_before_harvest():
    ripening = crop(stages=stages((4, 1), (5, 1), (5, 31), (7, 30), maturity=(8, 19)))
    assert crops.kc(ripening, date(2023, 8, 9)) == pytest.approx(0.9)
    assert crops.kc(ripening, date(2023, 8, 19)) == pytest.approx(0.7)
    assert crops.kc(ripening, date(2023, 8, 25)) == pytest.approx(0.7)
    assert crops.kc(ripening, date(2023, 8, 31)) == pytest.approx(0.7)
    assert crops.kc(ripening, date(2023, 9, 1)) == pytest.approx(0.3)


def test_bare_field_and_off_season_use_the_bare_soil_coefficient():
    for day in (date(2023, 1, 1), date(2023, 6, 20), date(2024, 2, 29), date(2023, 12, 31)):
        assert crops.kc(BARE, day) == 0.3
    assert crops.kc(BARE, date(2023, 6, 20), bare_soil_kc=0.2) == 0.2
    assert crops.kc(WHEAT, date(2023, 8, 15), bare_soil_kc=0.2) == 0.2
    assert crops.kc(WHEAT, date(2022, 10, 12), bare_soil_kc=0.2) == pytest.approx(0.3)
    assert crops.kc(WHEAT, date(2023, 6, 1), bare_soil_kc=0.2) == pytest.approx(1.15)


def test_kc_is_deterministic():
    days = [date(2023, 4, 10), date(2023, 7, 15), date(2023, 11, 21)]
    assert [crops.kc(WHEAT, day) for day in days] == [crops.kc(WHEAT, day) for day in days]


def test_winter_season_crosses_the_turn_of_the_year():
    assert crosses_new_year(WHEAT.season) and not crosses_new_year(SPRING.season)
    season = DateRange(date(2022, 10, 5), date(2023, 8, 1))
    for day in (date(2022, 10, 5), date(2022, 12, 31), date(2023, 1, 1), date(2023, 8, 1)):
        assert crops.season_on(WHEAT, day) == season
        assert crops.in_season(WHEAT, day)
    for day in (date(2022, 10, 4), date(2023, 8, 2), date(2023, 10, 4)):
        assert crops.season_on(WHEAT, day) is None
        assert not crops.in_season(WHEAT, day)
    leap = crops.season_on(WHEAT, date(2024, 2, 29))
    assert leap == DateRange(date(2023, 10, 5), date(2024, 8, 1))
    assert leap.days == 302
    assert season.days == 301


def test_last_season_is_the_running_one_or_the_one_just_finished():
    finished = DateRange(date(2022, 10, 5), date(2023, 8, 1))
    assert crops.last_season(WHEAT, date(2023, 6, 20)) == finished
    assert crops.last_season(WHEAT, date(2023, 8, 15)) == finished
    assert crops.last_season(WHEAT, date(2023, 10, 4)) == finished
    running = DateRange(date(2023, 10, 5), date(2024, 8, 1))
    assert crops.last_season(WHEAT, date(2023, 11, 15)) == running
    spring_2022 = DateRange(date(2022, 4, 1), date(2022, 8, 31))
    spring_2023 = DateRange(date(2023, 4, 1), date(2023, 8, 31))
    assert crops.last_season(SPRING, date(2023, 3, 31)) == spring_2022
    assert crops.last_season(SPRING, date(2023, 11, 15)) == spring_2023


def test_critical_period():
    critical = DateRange(date(2023, 5, 11), date(2023, 7, 10))
    assert crops.critical_period_on(WHEAT, date(2023, 5, 11)) == critical
    assert crops.critical_period_on(WHEAT, date(2023, 7, 10)) == critical
    assert crops.critical_period_on(WHEAT, date(2023, 5, 10)) is None
    assert crops.critical_period_on(WHEAT, date(2023, 7, 11)) is None
    assert crops.last_critical_period(WHEAT, date(2023, 6, 20)) == critical
    assert crops.last_critical_period(WHEAT, date(2023, 11, 15)) == critical
    earlier = DateRange(date(2022, 5, 11), date(2022, 7, 10))
    assert crops.last_critical_period(WHEAT, date(2023, 5, 10)) == earlier
    assert critical.midpoint == date(2023, 6, 10) and critical.days == 61


def test_cycle_offset_wraps_over_the_turn_of_the_year():
    assert cycle_offset(md(9, 25), md(9, 25)) == 0
    assert cycle_offset(md(9, 25), md(7, 31)) == 309
    assert cycle_offset(md(4, 1), md(8, 31)) == 152


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"stages": stages((4, 1), (6, 1), (5, 31), (7, 30))}, "follow each other"),
        ({"stages": stages((4, 1), (5, 1), (5, 31), (9, 15))}, "follow each other"),
        ({"stages": stages((4, 1), (5, 1), (5, 31), (7, 30), (7, 1))}, "follow each other"),
        ({"stages": stages((4, 1), (5, 1), (5, 31), (7, 30), (9, 5))}, "follow each other"),
        ({"critical_period": period((8, 15), (9, 15))}, "inside the season"),
        ({"critical_period": period((6, 30), (6, 1))}, "inside the season"),
        ({"season": period((2, 29), (8, 31))}, "every year"),
        ({"season": period((4, 1), (4, 1))}, "longer than one day"),
        ({"kc_mid": 0.0}, "positive crop coefficient"),
        ({"root_depth_m": (1.5, 1.0)}, "ordered range"),
        ({"depletion_fraction": 1.0}, "between 0 and 1"),
    ],
    ids=[
        "stages-swapped",
        "stage-after-harvest",
        "maturity-before-late-stage",
        "maturity-after-harvest",
        "critical-after-harvest",
        "critical-reversed",
        "29-february",
        "one-day-season",
        "zero-kc",
        "root-range-reversed",
        "depletion-out-of-range",
    ],
)
def test_incoherent_crop_is_rejected(changes: dict, message: str):
    with pytest.raises(ValidationError, match=message):
        growth(**changes)
