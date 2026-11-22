"""Crop coefficient curves, seasons and critical periods of real catalogue crops."""

from datetime import date

import pytest

from app.catalog import crops
from app.catalog.periods import DateRange


@pytest.mark.parametrize(
    ("crop_id", "day", "expected"),
    [
        # Grain maize: Kc ini equals the bare-soil value, so sowing changes nothing.
        ("maize", date(2023, 4, 27), 0.3),
        ("maize", date(2023, 5, 28), 0.3),  # development starts
        ("maize", date(2023, 6, 17), 0.75),  # half of the development (20 of 40 days)
        ("maize", date(2023, 7, 7), 1.2),
        ("maize", date(2023, 8, 26), 1.2),  # late season starts
        ("maize", date(2023, 9, 10), 1.2 - 0.6 * 15 / 29),
        ("maize", date(2023, 9, 24), 0.6),  # maturity
        ("maize", date(2023, 10, 18), 0.6),  # harvest
        ("maize", date(2023, 10, 19), 0.3),
        # Silage maize has no maturity date: the fall lasts until harvest.
        ("maize_silage", date(2023, 9, 2), 1.125),
        ("maize_silage", date(2023, 9, 9), 1.05),
        ("maize_silage", date(2023, 9, 10), 0.3),
        # Spring barley: emergence is also the start of development.
        ("spring_barley", date(2023, 3, 29), 0.3),
        ("spring_barley", date(2023, 4, 14), 0.3),
        ("spring_barley", date(2023, 5, 11), 0.3 + 0.85 * 27 / 53),
        ("spring_barley", date(2023, 6, 6), 1.15),
        ("spring_barley", date(2023, 7, 6), 0.7),
        ("spring_barley", date(2023, 8, 2), 0.25),
        # Potato: Kc rises from bare soil to Kc ini during the 30 days after planting.
        ("potato", date(2023, 5, 5), 0.4),
        ("potato", date(2023, 5, 20), 0.5),
        ("potato", date(2023, 6, 24), 1.15),
        ("potato", date(2023, 9, 12), 0.75),
        ("potato", date(2023, 9, 24), 0.75),
        # Grassland: growing period from April to September.
        ("grassland", date(2023, 3, 31), 0.3),
        ("grassland", date(2023, 4, 11), 0.95),
        ("grassland", date(2023, 5, 1), 1.05),
        ("grassland", date(2023, 9, 30), 1.0),
    ],
)
def test_kc_of_catalogue_spring_crops(crop_id: str, day: date, expected: float):
    assert crops.kc(crops.get_crop(crop_id), day) == pytest.approx(expected)


def test_seasons_and_critical_periods_of_catalogue_crops():
    maize = crops.get_crop("maize")
    assert crops.season_on(maize, date(2023, 6, 20)) == DateRange(
        date(2023, 4, 28), date(2023, 10, 18)
    )
    assert crops.critical_period_on(maize, date(2023, 6, 20)) is None
    assert crops.critical_period_on(maize, date(2023, 7, 20)) == DateRange(
        date(2023, 7, 1), date(2023, 8, 31)
    )
    assert not crops.in_season(maize, date(2023, 4, 27))
    rapeseed = crops.get_crop("winter_rapeseed")
    assert crops.season_on(rapeseed, date(2023, 1, 15)) == DateRange(
        date(2022, 8, 30), date(2023, 7, 20)
    )
    assert crops.last_critical_period(rapeseed, date(2023, 6, 20)) == DateRange(
        date(2023, 4, 10), date(2023, 5, 31)
    )
    for crop_id in ("onion", "cabbage", "beetroot", "tomato", "cucumber"):
        vegetable = crops.get_crop(crop_id)
        season = crops.last_season(vegetable, date(2023, 12, 31))
        critical = crops.last_critical_period(vegetable, date(2023, 12, 31))
        # The shared critical period of vegetables is cut to the season of each.
        assert critical.start >= max(season.start, date(2023, 4, 15))
        assert critical.end <= min(season.end, date(2023, 9, 30))
