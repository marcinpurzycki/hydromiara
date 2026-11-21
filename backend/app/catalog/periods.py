"""Calendar arithmetic for periods that repeat every year.

A period is given by two month-day pairs and may cross the turn of the year
(a winter crop is sown in autumn and harvested the next summer). The functions
are pure: they take the day they are asked about and never read the clock.
"""

from datetime import date
from typing import NamedTuple

from app.contracts.catalog import MonthDay, YearlyPeriod

# A year without 29 February, used to measure distances inside the yearly cycle.
_REFERENCE_YEAR = 2001
_CYCLE_DAYS = 365


class DateRange(NamedTuple):
    """One occurrence of a yearly period; both ends are inclusive."""

    start: date
    end: date

    def __contains__(self, day: object) -> bool:
        return isinstance(day, date) and self.start <= day <= self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def midpoint(self) -> date:
        """Middle day; for an even number of days the earlier of the two."""
        return self.start + (self.end - self.start) // 2


def is_every_year(moment: MonthDay) -> bool:
    """False for 29 February and for days that do not exist (30 February, 31 April)."""
    try:
        date(_REFERENCE_YEAR, moment.month, moment.day)
    except ValueError:
        return False
    return True


def in_year(moment: MonthDay, year: int) -> date:
    return date(year, moment.month, moment.day)


def on_or_after(moment: MonthDay, day: date) -> date:
    """First date with the given month and day that is not earlier than `day`."""
    candidate = in_year(moment, day.year)
    return candidate if candidate >= day else in_year(moment, day.year + 1)


def cycle_offset(start: MonthDay, moment: MonthDay) -> int:
    """Days from `start` to the next `moment`, counted in a year without 29 February."""
    first = in_year(start, _REFERENCE_YEAR).timetuple().tm_yday
    second = in_year(moment, _REFERENCE_YEAR).timetuple().tm_yday
    return (second - first) % _CYCLE_DAYS


def crosses_new_year(period: YearlyPeriod) -> bool:
    start, end = period.start, period.end
    return (end.month, end.day) < (start.month, start.day)


def occurrence_starting_in(period: YearlyPeriod, year: int) -> DateRange:
    """The occurrence whose first day falls in the given calendar year."""
    start = in_year(period.start, year)
    return DateRange(start, on_or_after(period.end, start))


def occurrence_containing(period: YearlyPeriod, day: date) -> DateRange | None:
    """The occurrence that includes `day`, or None when the day is outside the period."""
    for year in (day.year - 1, day.year):
        occurrence = occurrence_starting_in(period, year)
        if day in occurrence:
            return occurrence
    return None


def last_occurrence(period: YearlyPeriod, day: date) -> DateRange:
    """The latest occurrence that started on or before `day`; it may still be running."""
    occurrence = occurrence_starting_in(period, day.year)
    if occurrence.start > day:
        occurrence = occurrence_starting_in(period, day.year - 1)
    return occurrence
