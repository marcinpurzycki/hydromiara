"""Current water status: the state of the root zone on the analysis date.

One of the two verdicts of a report. It is computed only from the last day of
the balance and never mixed with the multi-year susceptibility. The deficit
level follows the stress coefficient Ks of that day (FAO-56 eq. 84) through
the thresholds in `params`.

Not assessed (level None, with a reason) when the series has no day up to the
analysis date, and for the field without a crop: no crop means no depletion
fraction, so no stress coefficient; the state of the soil water store is still
reported.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.contracts.common import Scalar
from app.engine.balance import WaterBalance
from app.engine.params import DEFAULT_PARAMS, DEFICIT_LEVEL_LABELS, EngineParams

NotAssessedReason = Literal["no_weather", "no_crop"]


def level_label(level: int) -> str:
    """Polish name of a deficit level 0-3."""
    return DEFICIT_LEVEL_LABELS[level]


def current_level(ks: float, params: EngineParams = DEFAULT_PARAMS) -> int:
    """Deficit level 0-3 for a stress coefficient; each threshold is inclusive."""
    for level, lowest_ks in enumerate(params.current_level_min_ks):
        if ks >= lowest_ks:
            return level
    return len(params.current_level_min_ks)


@dataclass(frozen=True)
class CurrentVerdict:
    """Current water status and the numbers behind it (unrounded)."""

    deficit_level: int | None
    label: str | None
    not_assessed_reason: NotAssessedReason | None
    # Last day with weather; the state below is the end of that day.
    state_date: date | None
    # Days between that day and the analysis date (0 = up to date).
    days_behind: int | None
    stress_coefficient: float | None
    depletion_mm: float | None
    total_available_water_mm: float
    readily_available_water_mm: float | None
    # Consecutive stress days ending on the state date.
    stress_run_days: int
    # Sums over the `recent_days` calendar days ending on the state date.
    recent_days: int
    precipitation_recent_mm: float | None
    et0_recent_mm: float | None
    # Days of that window without a complete weather record.
    recent_days_without_weather: int

    @property
    def assessed(self) -> bool:
        return self.deficit_level is not None

    @property
    def depletion_share(self) -> float | None:
        """Used part of the total available water, 0-1."""
        if self.depletion_mm is None:
            return None
        return self.depletion_mm / self.total_available_water_mm

    def details(self) -> dict[str, Scalar]:
        """Rounded values for the report, units in the key names."""
        n = self.recent_days
        share = self.depletion_share
        return {
            "depletion_mm": _rounded(self.depletion_mm),
            "readily_available_water_mm": _rounded(self.readily_available_water_mm),
            "total_available_water_mm": _rounded(self.total_available_water_mm),
            "depletion_pct": None if share is None else round(100 * share),
            "stress_coefficient": _rounded(self.stress_coefficient, 2),
            "stress_run_days": self.stress_run_days,
            f"precipitation_{n}d_mm": _rounded(self.precipitation_recent_mm),
            f"et0_{n}d_mm": _rounded(self.et0_recent_mm),
        }


def _rounded(value: float | None, digits: int = 0) -> float | int | None:
    if value is None:
        return None
    return round(value, digits) if digits else round(value)


def current_status(
    balance: WaterBalance, params: EngineParams = DEFAULT_PARAMS
) -> CurrentVerdict:
    """Current water status from the balance; uses only its last days."""
    zone = balance.root_zone
    last = balance.last
    if last is None:
        return CurrentVerdict(
            deficit_level=None,
            label=None,
            not_assessed_reason="no_weather",
            state_date=None,
            days_behind=None,
            stress_coefficient=None,
            depletion_mm=None,
            total_available_water_mm=zone.taw_mm,
            readily_available_water_mm=zone.raw_mm,
            stress_run_days=0,
            recent_days=params.recent_days,
            precipitation_recent_mm=None,
            et0_recent_mm=None,
            recent_days_without_weather=params.recent_days,
        )

    has_crop = zone.depletion_fraction is not None
    ks = zone.stress_coefficient(last.depletion_mm) if has_crop else None
    level = None if ks is None else current_level(ks, params)

    run = 0
    for day in reversed(balance.days):
        if not day.stressed:
            break
        run += 1

    window_start = last.date - timedelta(days=params.recent_days - 1)
    recent = balance.between(window_start, last.date)
    return CurrentVerdict(
        deficit_level=level,
        label=None if level is None else level_label(level),
        not_assessed_reason=None if has_crop else "no_crop",
        state_date=last.date,
        days_behind=balance.days_behind,
        stress_coefficient=ks,
        depletion_mm=last.depletion_mm,
        total_available_water_mm=zone.taw_mm,
        readily_available_water_mm=zone.raw_mm,
        stress_run_days=run,
        recent_days=params.recent_days,
        precipitation_recent_mm=sum(day.precipitation_mm for day in recent),
        et0_recent_mm=sum(day.et0_mm for day in recent),
        recent_days_without_weather=params.recent_days - sum(day.complete for day in recent),
    )
