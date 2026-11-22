"""Historical course: year by year, what grew on the parcel and how it fared for water.

It exists only when a crop history was given and stands next to the multi-year
susceptibility, never in its place. The susceptibility, the current status,
the causes, the recommendations and the irrigation part do not read it.

Rules, all applied to data already stored with the analysis:

- The years are the years of the multi-year window of the crop of the
  analysis (the years of its critical periods). A year the history does not
  name takes the crop of the analysis; years outside the window are ignored
  here (the API refuses them before they are stored).
- A crop belongs to the year in which its critical period begins. For a
  winter crop that is the year of its harvest: the season sown in the autumn
  before is the season of that year.
- The year is judged by the measure of a deficit year of the susceptibility,
  with the same parameters, on a balance run for the crop of that year over
  the whole weather series. The balances of different crops are separate:
  the soil water a year starts with is the one that crop would have left had
  it grown in the years before as well, not the one left by the crop the
  history names for the year before. A year of the crop of the analysis is
  therefore exactly the year of the susceptibility.
- A history that names no year of the window and does not say "the same crop
  every year" is treated as not given.
- A year is not assessed when the field had no crop (no rule gives a deficit
  level for it), when its critical period has no weather, or when the
  critical period of its crop begins after the analysis date.
- The satellite reading of a year is the newest usable scene of that calendar
  year not later than the analysis date. It is only described: with the crop
  of the year known, the note can say whether the scene shows that crop in
  its season or only the cover of the field.

Pure and deterministic: no network, clock or state. Days after the analysis
date are never read.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import get_crop
from app.catalog.periods import DateRange, occurrence_containing, occurrence_starting_in
from app.contracts.analyses import CropHistory
from app.contracts.source_data import SatelliteData, SatelliteScene, SourceData
from app.engine.assessment import WaterAssessment
from app.engine.balance import WaterBalance, run_balance
from app.engine.consistency_satellite import usable
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.root_zone import root_zone
from app.engine.susceptibility import YearResult, assess_period, window_periods

CropLookup = Callable[[str], CatalogCrop]
NotAssessed = Literal["no_crop", "no_weather", "not_started"]


@dataclass(frozen=True)
class CourseYear:
    """One year of the window: the crop of that year and its critical period."""

    year: int
    crop: CatalogCrop
    # True when the history names the year; False when it took the crop of the analysis.
    given: bool
    # True when the crop of the year is the crop of the analysis.
    same_crop: bool
    # None for the field without a crop.
    critical_period: DateRange | None
    not_assessed: NotAssessed | None
    # True when the critical period ends after the analysis date.
    partial: bool
    deficit: bool
    stress_days: int
    # Newest usable scene of the calendar year; None when there is none.
    scene: SatelliteScene | None
    # Whether the scene lies in the season of the crop of this year; None
    # without a scene and for the field without a crop.
    scene_in_season: bool | None

    @property
    def assessed(self) -> bool:
        return self.not_assessed is None


@dataclass(frozen=True)
class CourseResult:
    """The historical course of one analysis."""

    analysis_date: date
    # True when the history says the crop of the analysis grew every year.
    same_every_year: bool
    years: tuple[CourseYear, ...]

    @property
    def assessed_years(self) -> int:
        return sum(year.assessed for year in self.years)

    @property
    def deficit_years(self) -> int:
        return sum(year.deficit for year in self.years if year.assessed)

    @property
    def other_crop_years(self) -> tuple[int, ...]:
        """Years in which the history names another crop than the analysis."""
        return tuple(year.year for year in self.years if year.given and not year.same_crop)


def window_years(
    crop: CatalogCrop, analysis_date: date, params: EngineParams = DEFAULT_PARAMS
) -> tuple[int, ...]:
    """Years a crop history can name, oldest first; empty for the field without a crop."""
    return tuple(period.start.year for period in window_periods(crop, analysis_date, params))


def years_outside_window(
    history: CropHistory,
    crop: CatalogCrop,
    analysis_date: date,
    params: EngineParams = DEFAULT_PARAMS,
) -> tuple[int, ...]:
    """Years named by the history that are not years of the multi-year window."""
    window = set(window_years(crop, analysis_date, params))
    return tuple(sorted(year for year in history.years or {} if year not in window))


def _scene_of(
    satellite: SatelliteData | None, year: int, analysis_date: date
) -> SatelliteScene | None:
    if satellite is None:
        return None
    scenes = [
        scene
        for scene in satellite.scenes
        if scene.date.year == year and scene.date <= analysis_date and usable(scene)
    ]
    return max(scenes, key=lambda scene: scene.date, default=None)


def _in_season(
    crop: CatalogCrop, period: DateRange | None, scene: SatelliteScene | None
) -> bool | None:
    """Whether the scene lies in the season that holds the critical period of the year."""
    if scene is None or period is None or crop.season is None:
        return None
    season = occurrence_containing(crop.season, period.start)
    return season is not None and scene.date in season


def _year(
    year: int,
    crop: CatalogCrop,
    given: bool,
    same_crop: bool,
    result: YearResult | None,
    scene: SatelliteScene | None,
    analysis_date: date,
) -> CourseYear:
    period = None if result is None else result.critical_period
    not_assessed: NotAssessed | None = None
    if result is None:
        not_assessed = "no_crop"
    elif period.start > analysis_date:
        not_assessed = "not_started"
    elif not result.assessed:
        not_assessed = "no_weather"
    judged = result is not None and not_assessed is None
    return CourseYear(
        year=year,
        crop=crop,
        given=given,
        same_crop=same_crop,
        critical_period=period,
        not_assessed=not_assessed,
        partial=judged and result.partial,
        deficit=judged and result.deficit,
        stress_days=result.stress_days if judged else 0,
        scene=scene,
        scene_in_season=_in_season(crop, period, scene),
    )


def historical_course(
    source_data: SourceData,
    assessment: WaterAssessment,
    crop: CatalogCrop,
    history: CropHistory | None,
    params: EngineParams = DEFAULT_PARAMS,
    *,
    lookup: CropLookup = get_crop,
) -> CourseResult | None:
    """The historical course, or None when no history was given.

    `assessment` is the assessment of `crop` on the same source data; its
    years are reused for the years in which that crop grew. `lookup` resolves
    the crop identifiers of the history. None also for the field without a
    crop, which has no multi-year window (only "the same every year" could be
    said about it, and there is nothing to show then).
    """
    analysis_date = assessment.analysis_date
    years = window_years(crop, analysis_date, params)
    if history is None or not years:
        return None
    named = {year: crop_id for year, crop_id in (history.years or {}).items() if year in years}
    # An empty form, or "not the same every year" without any year, says nothing.
    if not named and not history.same_every_year:
        return None
    of_analysis = {result.year: result for result in assessment.multiyear_susceptibility.years}
    balances: dict[str, WaterBalance] = {}

    def result_for(year: int, grown: CatalogCrop) -> YearResult | None:
        if grown.critical_period is None:
            return None
        if grown.id == crop.id and year in of_analysis:
            return of_analysis[year]
        if grown.id not in balances:
            zone = root_zone(source_data.soil, grown, params)
            balances[grown.id] = run_balance(
                source_data.weather.days, grown, zone, analysis_date, params
            )
        period = occurrence_starting_in(grown.critical_period, year)
        return assess_period(balances[grown.id], period, params)

    course = []
    for year in years:
        given = year in named
        grown = lookup(named[year]) if given else crop
        scene = _scene_of(source_data.satellite, year, analysis_date)
        course.append(
            _year(
                year, grown, given, grown.id == crop.id, result_for(year, grown), scene,
                analysis_date,
            )
        )
    return CourseResult(
        analysis_date=analysis_date,
        same_every_year=bool(history.same_every_year),
        years=tuple(course),
    )
