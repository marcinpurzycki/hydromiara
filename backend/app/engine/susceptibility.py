"""Multi-year susceptibility: in how many of the last years the crop lacked water.

One of the two verdicts of a report, independent of the current status. The
window is the last `window_years` critical periods of the crop that began on
or before the analysis date; the latest one may be still running and is then
partial (counted only up to the analysis date). A year is a deficit year when
its critical period has at least the configured number of stress days.

Not assessed (level None, with a reason) for the field without a crop, which
has no critical period, and when no year of the window has weather.

The level thresholds are counts of years on the full window scale; when fewer
years could be assessed, the counts are not rescaled.
"""

from dataclasses import dataclass
from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import last_critical_period
from app.catalog.periods import DateRange, occurrence_starting_in
from app.contracts.common import Scalar
from app.engine.balance import WaterBalance
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.verdicts import NotAssessedReason, level_label

_MONTH_KEYS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def susceptibility_level(deficit_years: int, params: EngineParams = DEFAULT_PARAMS) -> int:
    """Deficit level 0-3 for a number of deficit years; each threshold is inclusive."""
    return sum(deficit_years >= lowest for lowest in params.susceptibility_level_min_years)


@dataclass(frozen=True)
class YearResult:
    """One year of the window: the critical period of the crop in that year."""

    year: int
    critical_period: DateRange
    # False when no day of the elapsed critical period has weather.
    assessed: bool
    # True when the critical period ends after the analysis date.
    partial: bool
    deficit: bool
    stress_days: int
    # Calendar days of the critical period up to the analysis date.
    critical_period_days: int
    # Those of them that have a complete weather record.
    days_with_weather: int
    # Sums over the configured months of the year, up to the analysis date.
    sum_months: tuple[int, int]
    precipitation_mm: float | None
    climatic_water_balance_mm: float | None

    def values(self) -> dict[str, Scalar]:
        """Rounded values for the report, units in the key names."""
        months = f"{_MONTH_KEYS[self.sum_months[0] - 1]}_{_MONTH_KEYS[self.sum_months[1] - 1]}"
        balance, rain = self.climatic_water_balance_mm, self.precipitation_mm
        return {
            "stress_days": self.stress_days,
            "critical_period_days": self.critical_period_days,
            "days_with_weather": self.days_with_weather,
            f"climatic_water_balance_{months}_mm": None if balance is None else round(balance),
            f"precipitation_{months}_mm": None if rain is None else round(rain),
        }


@dataclass(frozen=True)
class SusceptibilityVerdict:
    """Multi-year susceptibility and the years behind it."""

    deficit_level: int | None
    label: str | None
    not_assessed_reason: NotAssessedReason | None
    deficit_years: int
    # Years that could be assessed; years without weather are left out.
    total_years: int
    # All years of the window, oldest first, including those not assessed.
    years: tuple[YearResult, ...]

    @property
    def assessed(self) -> bool:
        return self.deficit_level is not None


def window_periods(
    crop: CatalogCrop, analysis_date: date, params: EngineParams = DEFAULT_PARAMS
) -> tuple[DateRange, ...]:
    """Critical periods of the window, oldest first; empty for the field without a crop."""
    latest = last_critical_period(crop, analysis_date)
    if latest is None or crop.critical_period is None:
        return ()
    first_year = latest.start.year - params.window_years + 1
    return tuple(
        occurrence_starting_in(crop.critical_period, year)
        for year in range(first_year, latest.start.year + 1)
    )


def _year_result(
    balance: WaterBalance, period: DateRange, analysis_date: date, params: EngineParams
) -> YearResult:
    elapsed_end = min(period.end, analysis_date)
    days = balance.between(period.start, elapsed_end)
    stress_days = sum(day.stressed for day in days)

    year = period.start.year
    first_month, last_month = params.climatic_balance_months
    sum_start = date(year, first_month, 1)
    sum_end = date(year + (last_month == 12), last_month % 12 + 1, 1)
    summed = [day for day in balance.between(sum_start, analysis_date) if day.date < sum_end]
    return YearResult(
        year=year,
        critical_period=period,
        assessed=bool(days),
        partial=period.end > analysis_date,
        deficit=stress_days >= params.deficit_year_min_stress_days,
        stress_days=stress_days,
        critical_period_days=(elapsed_end - period.start).days + 1,
        days_with_weather=sum(day.complete for day in days),
        sum_months=params.climatic_balance_months,
        precipitation_mm=sum(day.precipitation_mm for day in summed) if summed else None,
        climatic_water_balance_mm=(
            sum(day.precipitation_mm - day.et0_mm for day in summed) if summed else None
        ),
    )


def multiyear_susceptibility(
    balance: WaterBalance,
    crop: CatalogCrop,
    params: EngineParams = DEFAULT_PARAMS,
) -> SusceptibilityVerdict:
    """Multi-year susceptibility of the crop from its balance.

    The balance must have been run for the same crop; its analysis date sets
    the window.
    """
    analysis_date = balance.analysis_date
    periods = window_periods(crop, analysis_date, params)
    if not periods:
        return SusceptibilityVerdict(
            deficit_level=None,
            label=None,
            not_assessed_reason="no_crop",
            deficit_years=0,
            total_years=0,
            years=(),
        )
    years = tuple(_year_result(balance, period, analysis_date, params) for period in periods)
    assessed = [year for year in years if year.assessed]
    deficit_years = sum(year.deficit for year in assessed)
    level = susceptibility_level(deficit_years, params) if assessed else None
    return SusceptibilityVerdict(
        deficit_level=level,
        label=None if level is None else level_label(level),
        not_assessed_reason=None if assessed else "no_weather",
        deficit_years=deficit_years,
        total_years=len(assessed),
        years=years,
    )
