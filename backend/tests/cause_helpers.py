"""Helpers for the cause tests: assessments and terrain results with chosen values."""

from datetime import date

from app.catalog.periods import DateRange
from app.engine.assessment import WaterAssessment
from app.engine.root_zone import RootZone
from app.engine.susceptibility import SusceptibilityVerdict, YearResult
from app.engine.terrain_analysis import TerrainAnalysis
from app.engine.verdicts import CurrentVerdict, level_label
from tests.engine_helpers import balance_with_stress

DAY = date(2023, 6, 20)


def zone(mm_per_m: float = 180.0, source: str = "soil_profile", covered: float = 100.0) -> RootZone:
    return RootZone(
        depth_cm=100.0,
        taw_mm=mm_per_m,
        depletion_fraction=0.55,
        capacity_source=source,
        covered_cm=covered,
    )


def year(number: int, deficit: bool, rain: float | None = 200.0, et0: float = 400.0) -> YearResult:
    """One assessed year with April-July sums: rain and ET0."""
    return YearResult(
        year=number,
        critical_period=DateRange(start=date(number, 5, 15), end=date(number, 6, 30)),
        assessed=True,
        partial=number == DAY.year,
        deficit=deficit,
        stress_days=20 if deficit else 0,
        critical_period_days=47,
        days_with_weather=47,
        sum_months=(4, 7),
        precipitation_mm=rain,
        climatic_water_balance_mm=None if rain is None else rain - et0,
    )


def current(level: int | None, rain: float | None = 20.0, et0: float | None = 100.0) -> CurrentVerdict:
    assessed = level is not None
    return CurrentVerdict(
        deficit_level=level,
        label=level_label(level) if assessed else None,
        not_assessed_reason=None if assessed else "no_crop",
        state_date=DAY,
        days_behind=0,
        stress_coefficient=0.5 if assessed else None,
        depletion_mm=80.0,
        total_available_water_mm=180.0,
        readily_available_water_mm=99.0 if assessed else None,
        stress_run_days=0,
        recent_days=30,
        precipitation_recent_mm=rain,
        et0_recent_mm=et0,
        recent_days_without_weather=0,
    )


def multiyear(level: int | None, years: tuple[YearResult, ...] = ()) -> SusceptibilityVerdict:
    assessed = level is not None
    return SusceptibilityVerdict(
        deficit_level=level,
        label=level_label(level) if assessed else None,
        not_assessed_reason=None if assessed else "no_crop",
        deficit_years=sum(item.deficit for item in years),
        total_years=len(years),
        years=years,
    )


def window(deficit_years: int, rain: float | None = 200.0, et0: float = 400.0) -> tuple[YearResult, ...]:
    """Ten years ending in the analysis year; the first `deficit_years` are deficit years."""
    return tuple(
        year(2014 + index, index < deficit_years, rain if index < deficit_years else 320.0, et0)
        for index in range(10)
    )


def assessment(
    current_level: int | None = 2,
    multiyear_level: int | None = 2,
    *,
    root_zone: RootZone | None = None,
    years: tuple[YearResult, ...] | None = None,
    recent: tuple[float | None, float | None] = (20.0, 100.0),
    crop_id: str = "winter_wheat",
) -> WaterAssessment:
    used = root_zone or zone()
    if years is None:
        years = window(6) if multiyear_level else window(0)
    return WaterAssessment(
        crop_id=crop_id,
        analysis_date=DAY,
        root_zone=used,
        balance=balance_with_stress(date(2013, 9, 1), DAY, set(), zone=used),
        current_status=current(current_level, *recent),
        multiyear_susceptibility=multiyear(multiyear_level, years if multiyear_level is not None else ()),
    )


def terrain(
    slope: float | None = 3.0, error: float = 0.2, *, status: str = "ok", resolved: bool | None = None
) -> TerrainAnalysis:
    if status != "ok":
        return TerrainAnalysis(status=status, cells_inside=3, cells_used=3)
    resolved = slope >= 2.0 * error and slope > 0 if resolved is None else resolved
    return TerrainAnalysis(
        status="ok",
        cells_inside=30,
        cells_used=30,
        cell_size_m=(28.1, 30.9),
        covers_parcel=True,
        slope_pct=slope,
        slope_error_pct=error,
        direction_resolved=resolved,
        downhill_azimuth_deg=45.0 if resolved else None,
        downhill_label="północny wschód" if resolved else None,
        lowest_part="północno-wschodnia" if resolved else None,
        relief_m=4.2,
    )
