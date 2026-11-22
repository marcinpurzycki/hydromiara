"""Where the analysis date lies for the crop, and what follows from it.

Three questions are answered here, all from the crop catalogue and the water
balance, with no dates written in the code:

1. The state of the date (`season_status`): in the season, in the season but
   dormant (a winter crop between the end of its autumn emergence and the
   start of spring growth), outside the season, or no crop at all. Outside
   the season and in dormancy the current water status describes the soil
   water store, not the needs of the plant.
2. The date of the critical-period analysis (`critical_period_date`): the
   middle of the latest critical period whose middle day is not later than
   the analysis date. A period that is still running and has not reached its
   middle yet is skipped, so the result is never later than the analysis date
   and never needs data from the future.
3. The past season in numbers (`past_season`): stress days of the latest
   finished season and how the soil water store changed since its end. Only
   values the balance already holds; no thresholds of its own.

Dormancy is read from the growth stages of the crop: it is the stage between
the end of establishment and the start of development, and only when that
stage runs across the turn of the year (a crop sown in autumn). The first day
of dormancy is the day establishment ends; the day development starts is the
first day of growth again.

Pure and deterministic: no network, clock or state.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import last_critical_period, last_season
from app.catalog.periods import (
    DateRange,
    crosses_new_year,
    occurrence_containing,
    occurrence_starting_in,
)
from app.contracts.catalog import YearlyPeriod
from app.engine.balance import WaterBalance

DateState = Literal["in_season", "dormant", "out_of_season", "no_crop"]

# States in which the deficit level describes the soil water store.
STORE_STATES: frozenset[DateState] = frozenset({"dormant", "out_of_season"})


@dataclass(frozen=True)
class SeasonStatus:
    """The analysis date against the season of the crop."""

    state: DateState
    # Latest season sown on or before the date: the running one inside the
    # season (also in dormancy), the finished one outside it. None without a crop.
    last_season: DateRange | None
    # Latest season that ended before the date. None without a crop.
    finished_season: DateRange | None
    # The dormancy that includes the date; None in every other state.
    dormancy: DateRange | None

    @property
    def in_season(self) -> bool:
        """True also in dormancy: a dormant winter crop is in its season."""
        return self.state in ("in_season", "dormant")

    @property
    def store_assessed(self) -> bool:
        """True when the deficit level refers to the soil water store."""
        return self.state in STORE_STATES


def dormancy_period(crop: CatalogCrop) -> YearlyPeriod | None:
    """Yearly dormancy of the crop from its stage dates; None for a crop without one.

    The end of the returned period is the day development starts, which is
    itself no longer a day of dormancy.
    """
    if crop.growth is None:
        return None
    stages = crop.growth.stages.value
    stage = YearlyPeriod(start=stages.establishment_end, end=stages.development_start)
    return stage if crosses_new_year(stage) else None


def dormancy_on(crop: CatalogCrop, day: date) -> DateRange | None:
    """The dormancy that includes `day` (both ends inclusive), or None."""
    period = dormancy_period(crop)
    if period is None:
        return None
    stage = occurrence_containing(period, day)
    if stage is None or day == stage.end:
        return None
    return DateRange(stage.start, stage.end - timedelta(days=1))


def finished_season(crop: CatalogCrop, day: date) -> DateRange | None:
    """The latest season that ended before `day`; None for the field without a crop."""
    latest = last_season(crop, day)
    if latest is None or crop.season is None:
        return None
    if latest.end < day:
        return latest
    return occurrence_starting_in(crop.season, latest.start.year - 1)


def season_status(crop: CatalogCrop, day: date) -> SeasonStatus:
    """State of the date for the crop, with the dates of the seasons around it."""
    latest = last_season(crop, day)
    if latest is None:
        return SeasonStatus("no_crop", None, None, None)
    finished = finished_season(crop, day)
    if day not in latest:
        return SeasonStatus("out_of_season", latest, finished, None)
    dormancy = dormancy_on(crop, day)
    state: DateState = "in_season" if dormancy is None else "dormant"
    return SeasonStatus(state, latest, finished, dormancy)


def critical_period_for(crop: CatalogCrop, analysis_date: date) -> DateRange | None:
    """The latest critical period whose middle day is not later than the date."""
    period = last_critical_period(crop, analysis_date)
    if period is None or crop.critical_period is None:
        return None
    if period.midpoint > analysis_date:
        period = occurrence_starting_in(crop.critical_period, period.start.year - 1)
    return period


def critical_period_date(crop: CatalogCrop, analysis_date: date) -> date | None:
    """Analysis date of the critical-period analysis; None for the field without a crop.

    Never later than `analysis_date`; equal to it when the date already is the
    middle day of a critical period.
    """
    period = critical_period_for(crop, analysis_date)
    return None if period is None else period.midpoint


@dataclass(frozen=True)
class PastSeason:
    """The latest finished season and the soil water store since its end (unrounded)."""

    season: DateRange
    # The critical period that lies inside that season.
    critical_period: DateRange | None
    # Days of the season that are in the balance series.
    days_in_balance: int
    # Days of the season that ended with the depletion above the readily
    # available water (stress days of the balance).
    stress_days: int
    critical_period_stress_days: int
    # Root zone depletion at the end of the last day of the season; None when
    # the series has no record for that day.
    end_depletion_mm: float | None
    # Last day of the balance and the depletion at its end.
    state_date: date
    depletion_mm: float
    # Precipitation from the day after the season to the state date.
    precipitation_since_mm: float

    @property
    def store_change_mm(self) -> float | None:
        """Change of the soil water store since the season end; positive = rebuilt."""
        if self.end_depletion_mm is None:
            return None
        return self.end_depletion_mm - self.depletion_mm


def past_season(
    balance: WaterBalance, crop: CatalogCrop, status: SeasonStatus
) -> PastSeason | None:
    """Numbers of the latest finished season from the balance of the same crop.

    None when there is no finished season, or when the balance has no day of
    it (the weather series starts later) or no day at all.
    """
    season = status.finished_season
    last = balance.last
    if season is None or last is None:
        return None
    days = balance.between(season.start, season.end)
    if not days:
        return None
    critical = last_critical_period(crop, season.end)
    critical_days = () if critical is None else balance.between(critical.start, critical.end)
    at_end = days[-1]
    since = balance.between(season.end + timedelta(days=1), last.date)
    return PastSeason(
        season=season,
        critical_period=critical,
        days_in_balance=len(days),
        stress_days=sum(day.stressed for day in days),
        critical_period_stress_days=sum(day.stressed for day in critical_days),
        end_depletion_mm=at_end.depletion_mm if at_end.date == season.end else None,
        state_date=last.date,
        depletion_mm=last.depletion_mm,
        precipitation_since_mm=sum(day.precipitation_mm for day in since),
    )
