"""Helpers for the simulation tests: made-up crops and weather with chosen dry years.

The crops are built from the catalogue models and exist only in the tests;
their values are not agronomic data.
"""

from datetime import date, timedelta

from app.catalog.crop_model import CatalogCrop, CropGrowth, Sourced, StageDates
from app.contracts.catalog import MonthDay, YearlyPeriod
from app.contracts.source_data import WeatherDay
from tests.engine_helpers import weather_day

_TEST = "made up for the test"

MonthDayPair = tuple[int, int]
Period = tuple[MonthDayPair, MonthDayPair]

# Season and stage dates of the two shapes a made-up crop can take.
_SHAPES: dict[str, tuple[Period, tuple[MonthDayPair, ...]]] = {
    "winter": (((9, 25), (7, 31)), ((10, 27), (3, 16), (5, 5), (6, 30))),
    "spring": (((4, 20), (10, 10)), ((5, 10), (5, 25), (7, 1), (9, 1))),
}
EARLY: Period = ((5, 15), (6, 30))
LATE: Period = ((7, 1), (8, 20))


def _md(month: int, day: int) -> MonthDay:
    return MonthDay(month=month, day=day)


def _period(period: Period) -> YearlyPeriod:
    return YearlyPeriod(start=_md(*period[0]), end=_md(*period[1]))


def made_crop(
    crop_id: str,
    *,
    shape: str = "winter",
    critical: Period | None = None,
    kc_mid: float = 1.15,
    roots: tuple[float, float] = (1.5, 1.8),
    p: float = 0.55,
) -> CatalogCrop:
    """A crop of the given shape; the critical period defaults to the one of its shape."""
    season, stages = _SHAPES[shape]
    critical = critical or (EARLY if shape == "winter" else LATE)
    growth = CropGrowth(
        season=Sourced[YearlyPeriod](value=_period(season), provisional=_TEST),
        critical_period=Sourced[YearlyPeriod](value=_period(critical), provisional=_TEST),
        stages=Sourced[StageDates](
            value=StageDates(
                establishment_end=_md(*stages[0]),
                development_start=_md(*stages[1]),
                mid_start=_md(*stages[2]),
                late_start=_md(*stages[3]),
            ),
            provisional=_TEST,
        ),
        kc_ini=Sourced[float](value=0.4, provisional=_TEST),
        kc_mid=Sourced[float](value=kc_mid, provisional=_TEST),
        kc_end=Sourced[float](value=0.3, provisional=_TEST),
        root_depth_m=Sourced[tuple[float, float]](value=roots, provisional=_TEST),
        depletion_fraction=Sourced[float](value=p, provisional=_TEST),
    )
    return CatalogCrop(
        id=crop_id,
        name=f"Uprawa testowa {crop_id}",
        name_genitive=f"uprawy testowej {crop_id}",
        tile=False,
        growth=growth,
    )


def many_crops(count: int) -> list[CatalogCrop]:
    """Made-up crops that all differ: shape, crop coefficient, roots, depletion fraction."""
    crops = []
    for index in range(count):
        shape = "winter" if index % 2 == 0 else "spring"
        depth = 0.3 + 0.1 * (index % 9)
        crops.append(
            made_crop(
                f"made_{index:02d}",
                shape=shape,
                kc_mid=0.9 + 0.02 * index,
                roots=(depth, depth + 0.3),
                p=0.35 + 0.02 * (index % 11),
            )
        )
    return crops


def weather_with_dry_years(
    first: date, last: date, dry_years: set[int], missing: tuple[date, date] | None = None
) -> list[WeatherDay]:
    """Daily weather: a dry year has no rain at all, any other year rains every day.

    In a dry year the soil is emptied long before May, so every day of a
    critical period is a stress day; in a wet year none is. Days of `missing`
    (both ends inclusive) are absent from the series.
    """
    days = []
    day = first
    while day <= last:
        if missing is None or not missing[0] <= day <= missing[1]:
            dry = day.year in dry_years
            days.append(weather_day(day, 0.0 if dry else 10.0, 5.0 if dry else 1.0))
        day += timedelta(days=1)
    return days
