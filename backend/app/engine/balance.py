"""Daily soil water balance of the root zone (FAO-56, chapter 8).

For every day up to the analysis date, in this order:
  Ks      from the depletion at the end of the previous day      (eq. 84)
  ETc     = Ks * Kc * ET0                                         (eq. 80)
  Dr      = Dr of the previous day + ETc - P                      (eq. 85)
  DP      = the part of P that would push Dr below zero           (eq. 88)
  Dr      kept within 0..TAW                                      (eq. 86)

Simplifications against the full equation 85, the same as in the trial
calculation of this project: surface runoff, irrigation and capillary rise are
zero, so all precipitation enters the soil and any surplus above field capacity
drains the same day. A stress day is a day that ends with Dr above RAW.

Days after the analysis date are dropped before anything is computed, so later
data cannot change the result. A day without precipitation or without ET0
takes the missing term as 0 mm (it leaves the store unchanged) and is counted
in `incomplete_days`; days absent from the series are skipped (the state is
carried over) and counted in `missing_dates`.
"""

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import kc
from app.contracts.source_data import WeatherDay
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.root_zone import RootZone


@dataclass(frozen=True)
class DayBalance:
    """State of the root zone at the end of one day."""

    date: date
    # Terms as used in the balance: a missing value is 0 mm.
    precipitation_mm: float
    et0_mm: float
    kc: float
    # Stress coefficient that reduced the evapotranspiration of this day.
    ks: float
    etc_mm: float
    # Deep percolation: water above field capacity lost on this day.
    drainage_mm: float
    # Root zone depletion at the end of the day, 0 = field capacity.
    depletion_mm: float
    stressed: bool
    # False when precipitation or ET0 was missing in the source.
    complete: bool


@dataclass(frozen=True)
class WaterBalance:
    """The balance series for one crop on one parcel, up to the analysis date."""

    analysis_date: date
    root_zone: RootZone
    days: tuple[DayBalance, ...]
    # Days of the series with a missing precipitation or ET0 value.
    incomplete_days: int
    # Calendar days between the first day and the analysis date without a record.
    missing_dates: int

    @property
    def last(self) -> DayBalance | None:
        """The latest day with weather; the current state refers to it."""
        return self.days[-1] if self.days else None

    @property
    def days_behind(self) -> int | None:
        """How many days before the analysis date the series ends."""
        return None if not self.days else (self.analysis_date - self.days[-1].date).days

    def between(self, start: date, end: date) -> tuple[DayBalance, ...]:
        """Days from `start` to `end`, both inclusive."""
        left = bisect_left(self.days, start, key=lambda day: day.date)
        right = bisect_right(self.days, end, key=lambda day: day.date)
        return self.days[left:right]


def days_until(weather_days: Iterable[WeatherDay], analysis_date: date) -> list[WeatherDay]:
    """Weather days not later than the analysis date, in calendar order."""
    kept = sorted(
        (day for day in weather_days if day.date <= analysis_date), key=lambda day: day.date
    )
    for earlier, later in zip(kept, kept[1:]):
        if earlier.date == later.date:
            raise ValueError(f"weather series has two records for {earlier.date.isoformat()}")
    return kept


def run_balance(
    weather_days: Iterable[WeatherDay],
    crop: CatalogCrop,
    zone: RootZone,
    analysis_date: date,
    params: EngineParams = DEFAULT_PARAMS,
) -> WaterBalance:
    """Daily water balance of the crop's root zone up to the analysis date."""
    records = days_until(weather_days, analysis_date)
    taw = zone.taw_mm
    depletion = params.initial_depletion_share * taw
    days: list[DayBalance] = []
    incomplete = 0
    for record in records:
        complete = record.precipitation_mm is not None and record.et0_mm is not None
        incomplete += not complete
        precipitation = record.precipitation_mm or 0.0
        et0 = record.et0_mm or 0.0
        crop_kc = kc(crop, record.date, bare_soil_kc=params.bare_soil_kc)
        ks = zone.stress_coefficient(depletion)
        etc = ks * crop_kc * et0
        unbounded = depletion + etc - precipitation
        drainage = max(0.0, -unbounded)
        depletion = min(taw, max(0.0, unbounded))
        days.append(
            DayBalance(
                date=record.date,
                precipitation_mm=precipitation,
                et0_mm=et0,
                kc=crop_kc,
                ks=ks,
                etc_mm=etc,
                drainage_mm=drainage,
                depletion_mm=depletion,
                stressed=zone.is_stressed(depletion),
                complete=complete,
            )
        )
    span = (analysis_date - records[0].date).days + 1 if records else 0
    return WaterBalance(
        analysis_date=analysis_date,
        root_zone=zone,
        days=tuple(days),
        incomplete_days=incomplete,
        missing_dates=span - len(records),
    )
