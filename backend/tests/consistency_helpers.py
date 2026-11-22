"""Helpers for the consistency check tests: verdicts and comparison data made by hand."""

from dataclasses import replace
from datetime import date

from app.contracts.source_data import (
    CdiDekad,
    DroughtBackground,
    SatelliteData,
    SatelliteScene,
    SourceData,
)
from app.engine.assessment import WaterAssessment, assess_water
from app.engine.consistency import ConsistencyOutcome, check_consistency
from app.engine.params import DEFICIT_LEVEL_LABELS
from tests.engine_helpers import WHEAT, source_data, weather_from

# In the season of winter wheat; the comparison dekad is 11-20 June 2023.
IN_SEASON = date(2023, 6, 20)
DEKAD = date(2023, 6, 11)
# Outside the season of winter wheat (harvest 31 July, sowing 25 September).
OUT_OF_SEASON = date(2023, 8, 31)

_BASE = source_data(weather_from(date(2023, 6, 1), [(1.0, 3.0)] * 20))


def assessment_with(level: int | None, reason: str | None = None) -> WaterAssessment:
    """A real assessment whose current verdict is replaced by the given level."""
    assessment = assess_water(_BASE, WHEAT, IN_SEASON)
    verdict = replace(
        assessment.current_status,
        deficit_level=level,
        label=None if level is None else DEFICIT_LEVEL_LABELS[level],
        not_assessed_reason=reason,
    )
    return replace(assessment, current_status=verdict)


def cdi(*dekads: tuple[date, int | None]) -> DroughtBackground:
    return DroughtBackground(
        dekads=[CdiDekad(date=day, cdi_class=cdi_class) for day, cdi_class in dekads]
    )


def scene(day: date, ndvi: float | None = 0.71, ndmi: float | None = 0.23) -> SatelliteScene:
    return SatelliteScene(date=day, clear_share_pct=95, ndvi=ndvi, ndmi=ndmi)


def data(
    background: DroughtBackground | None = None, scenes: list[SatelliteScene] | None = None
) -> SourceData:
    satellite = None if scenes is None else SatelliteData(scenes=scenes)
    return _BASE.model_copy(update={"drought_background": background, "satellite": satellite})


def run(
    level: int | None,
    background: DroughtBackground | None = None,
    scenes: list[SatelliteScene] | None = None,
    *,
    day: date = IN_SEASON,
    crop=WHEAT,
    reason: str | None = None,
    **options,
) -> ConsistencyOutcome:
    return check_consistency(
        data(background, scenes), assessment_with(level, reason), crop, day, **options
    )
