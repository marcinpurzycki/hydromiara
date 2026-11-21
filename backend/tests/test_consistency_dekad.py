"""Which dekad of the drought indicator is compared: never one that ends after the date."""

from datetime import date, timedelta

import pytest

from app.engine.consistency_cdi import Dekad, comparison_dekad


@pytest.mark.parametrize(
    ("analysis_date", "start", "end"),
    [
        # First day of a dekad: the dekad has only begun, the previous one is used.
        (date(2023, 6, 1), date(2023, 5, 21), date(2023, 5, 31)),
        (date(2023, 6, 11), date(2023, 6, 1), date(2023, 6, 10)),
        (date(2023, 6, 21), date(2023, 6, 11), date(2023, 6, 20)),
        # Last day of a dekad: that dekad is complete.
        (date(2023, 6, 10), date(2023, 6, 1), date(2023, 6, 10)),
        (date(2023, 6, 20), date(2023, 6, 11), date(2023, 6, 20)),
        (date(2023, 6, 30), date(2023, 6, 21), date(2023, 6, 30)),
        # Inside a dekad.
        (date(2023, 6, 15), date(2023, 6, 1), date(2023, 6, 10)),
        (date(2023, 6, 29), date(2023, 6, 11), date(2023, 6, 20)),
        # The third dekad runs to the end of the month, whatever its length.
        (date(2023, 7, 30), date(2023, 7, 11), date(2023, 7, 20)),
        (date(2023, 7, 31), date(2023, 7, 21), date(2023, 7, 31)),
        # February, common and leap year.
        (date(2023, 2, 27), date(2023, 2, 11), date(2023, 2, 20)),
        (date(2023, 2, 28), date(2023, 2, 21), date(2023, 2, 28)),
        (date(2023, 3, 1), date(2023, 2, 21), date(2023, 2, 28)),
        (date(2024, 2, 28), date(2024, 2, 11), date(2024, 2, 20)),
        (date(2024, 2, 29), date(2024, 2, 21), date(2024, 2, 29)),
        (date(2024, 3, 5), date(2024, 2, 21), date(2024, 2, 29)),
        # Turn of the year.
        (date(2024, 1, 1), date(2023, 12, 21), date(2023, 12, 31)),
        (date(2023, 12, 31), date(2023, 12, 21), date(2023, 12, 31)),
        (date(2024, 1, 9), date(2023, 12, 21), date(2023, 12, 31)),
    ],
)
def test_latest_dekad_that_ended_by_the_analysis_date(analysis_date, start, end):
    assert comparison_dekad(analysis_date) == Dekad(start, end)


def test_dekad_never_ends_after_the_analysis_date_and_is_never_stale():
    day = date(2019, 12, 1)
    while day <= date(2024, 3, 31):
        dekad = comparison_dekad(day)
        assert dekad.start.day in (1, 11, 21)
        assert dekad.start <= dekad.end <= day
        # The day after the dekad starts the next one, which is not yet complete.
        assert (dekad.end + timedelta(days=1)).day in (1, 11, 21)
        assert (day - dekad.end).days <= 10
        day += timedelta(days=1)
