"""What the satellite scenes of an analysis say, as numbers. Pure and deterministic.

Three readings, none with absolute thresholds:

- cover of the field: the newest clear scene of the current window, always;
- change over the last weeks: the newest scene against the median of the
  earlier scenes of the window, significant from a fixed difference;
- comparison with earlier years: NDMI of the newest scene against the median
  of the years in which the crop history names the same crop.

The last two are made only inside the critical period of the crop: no source
dates the growth stages in which a fall of the indices is natural (ripening).
A winter crop whose field was bare in April does not match the scenes.

Scenes taken after the analysis date are never read.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Literal

from app.catalog.crop_model import CatalogCrop
from app.catalog.periods import DateRange, occurrence_containing
from app.contracts.analyses import CropHistory
from app.contracts.source_data import SatelliteData, SatelliteScene
from app.engine.satellite_crops import CropReading, Index
from app.sources import satellite_params as windows

Direction = Literal["falls", "steady", "rises"]
# What the reading says next to the water deficit of the balance.
Signal = Literal[
    "no_data",  # no scene in the current window
    "cover_only",  # outside the critical period, or a crop read only descriptively
    "not_enough_data",  # one scene only and no comparison with earlier years
    "confirms",  # deficit in the balance, NDMI falls or is lower than in earlier years
    "does_not_confirm",  # deficit in the balance, no such fall (plants react with a delay)
    "contradicts",  # no deficit in the balance, NDMI falls in the critical period
    "no_objection",  # no deficit in the balance, no fall
]


@dataclass(frozen=True)
class ReadingParams:
    """Thresholds of the reading; the windows are those of the satellite adapter."""

    # Smallest difference of an index counted as a change. Measured: clear
    # scenes at most 5 days apart differ by 0.06-0.13 at the 90th percentile.
    significant_change: float = 0.10
    # PROVISIONAL: no source; years of the same crop needed for the comparison.
    min_same_crop_years: int = 3
    # PROVISIONAL: own measurement on one parcel; a field of a winter crop
    # with a lower median NDVI of the April scenes does not match the crop.
    april_min_ndvi: float = 0.4
    history_years: int = windows.HISTORY_YEARS
    history_half_window_days: int = windows.HISTORY_HALF_WINDOW_DAYS


DEFAULT_READING_PARAMS = ReadingParams()


@dataclass(frozen=True)
class Change:
    """The newest scene against the median of the earlier scenes of the window."""

    index: Index
    difference: float
    direction: Direction
    earlier_scenes: int


@dataclass(frozen=True)
class YearsComparison:
    """NDMI of the newest scene against earlier years of the same crop."""

    # Years of the same crop that have a reading, oldest first.
    years: tuple[int, ...]
    # None when the years are fewer than the comparison needs.
    difference: float | None
    direction: Direction | None


@dataclass(frozen=True)
class Reading:
    newest: SatelliteScene | None
    earlier: tuple[SatelliteScene, ...]  # other scenes of the current window, newest first
    interpreted: bool  # True inside the critical period of the crop
    changes: tuple[Change, ...]
    years: YearsComparison | None  # None when not interpreted or without a crop history
    april_ndvi: float | None  # median NDVI of the April scenes of the season, if checked
    crop_mismatch: bool
    signal: Signal


def _direction(difference: float, params: ReadingParams) -> Direction:
    if difference <= -params.significant_change:
        return "falls"
    return "rises" if difference >= params.significant_change else "steady"


def _change(
    index: Index, newest: SatelliteScene, earlier: tuple[SatelliteScene, ...], params: ReadingParams
) -> Change | None:
    value = getattr(newest, index)
    before = [getattr(scene, index) for scene in earlier if getattr(scene, index) is not None]
    if value is None or not before:
        return None  # one scene is not enough for a conclusion
    difference = round(value - median(before), 4)
    return Change(index, difference, _direction(difference, params), len(before))


def same_crop_years(crop: CatalogCrop, history: CropHistory) -> frozenset[int] | None:
    """Years the history names with the crop of the analysis; None for all years.

    A year the history does not name does not count: the assumption "the same
    crop every year" serves the water balance and says nothing about what the
    scenes show.
    """
    if history.same_every_year:
        return None
    return frozenset(year for year, crop_id in (history.years or {}).items() if crop_id == crop.id)


def _years_back(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February in a year that has none
        return day.replace(year=day.year - years, day=28)


def _compare_years(
    newest: SatelliteScene,
    scenes: list[SatelliteScene],
    crop: CatalogCrop,
    analysis_date: date,
    named: frozenset[int] | None,
    params: ReadingParams,
) -> YearsComparison:
    """A crop belongs to the year in which its critical period begins."""
    half = timedelta(days=params.history_half_window_days)
    by_year: dict[int, float] = {}
    for back in range(1, params.history_years + 1):
        anchor = _years_back(analysis_date, back)
        period = occurrence_containing(crop.critical_period, anchor)
        if period is None or (named is not None and period.start.year not in named):
            continue
        values = [
            scene.ndmi
            for scene in scenes
            if anchor - half <= scene.date <= anchor + half and scene.ndmi is not None
        ]
        if values:
            by_year[period.start.year] = median(values)
    years = tuple(sorted(by_year))
    if newest.ndmi is None or len(years) < params.min_same_crop_years:
        return YearsComparison(years, None, None)
    difference = round(newest.ndmi - median(by_year.values()), 4)
    return YearsComparison(years, difference, _direction(difference, params))


def _signal(
    changes: tuple[Change, ...],
    years: YearsComparison | None,
    deficit: bool | None,
    rules: CropReading,
) -> Signal:
    if deficit is None or not rules.signals_deficit:
        return "cover_only"
    ndmi = next((change for change in changes if change.index == "ndmi"), None)
    compared = years is not None and years.direction is not None
    if ndmi is None and not compared:
        return "not_enough_data"
    falls = ndmi is not None and ndmi.direction == "falls"
    if deficit:
        return "confirms" if falls or (compared and years.direction == "falls") else "does_not_confirm"
    return "contradicts" if falls else "no_objection"


def read_satellite(
    satellite: SatelliteData | None,
    analysis_date: date,
    *,
    crop: CatalogCrop,
    rules: CropReading,
    season: DateRange | None,
    history: CropHistory | None,
    deficit: bool | None,
    window_days: int = windows.CURRENT_WINDOW_DAYS,
    params: ReadingParams = DEFAULT_READING_PARAMS,
) -> Reading:
    """The reading for an analysis.

    `season` is the running season of the crop (None outside it), `deficit`
    whether the balance finds a water deficit (None when it gives no level
    that refers to the crop). `history` is the crop history, if given.
    """
    usable = [
        scene
        for scene in (satellite.scenes if satellite else [])
        if scene.date <= analysis_date and (scene.ndvi is not None or scene.ndmi is not None)
    ]
    first_day = analysis_date - timedelta(days=window_days)
    current = sorted(
        (scene for scene in usable if scene.date >= first_day),
        key=lambda scene: scene.date,
        reverse=True,
    )
    if not current:
        return Reading(None, (), False, (), None, None, False, "no_data")
    newest, earlier = current[0], tuple(current[1:])
    critical = crop.critical_period
    interpreted = critical is not None and occurrence_containing(critical, analysis_date) is not None
    changes: tuple[Change, ...] = ()
    years = None
    if interpreted:
        found = (_change(index, newest, earlier, params) for index in rules.change_indices)
        changes = tuple(change for change in found if change is not None)
        if history is not None:
            named = same_crop_years(crop, history)
            years = _compare_years(newest, usable, crop, analysis_date, named, params)
    april = [
        scene.ndvi
        for scene in usable
        if rules.green_in_april and season is not None and scene.date in season
        and (scene.date.year, scene.date.month) == (analysis_date.year, 4)
        and scene.ndvi is not None
    ]  # fmt: skip
    april_ndvi = round(median(april), 4) if april else None
    return Reading(
        newest=newest,
        earlier=earlier,
        interpreted=interpreted,
        changes=changes,
        years=years,
        april_ndvi=april_ndvi,
        crop_mismatch=april_ndvi is not None and april_ndvi < params.april_min_ndvi,
        signal=_signal(changes, years, deficit, rules) if interpreted else "cover_only",
    )
