"""Irrigation part of the Report: whether, how much and when, from one day's state.

The answer uses only what the water balance holds for the analysis date: the
current water status with its deficit level, the root zone depletion Dr, the
readily available water RAW and the total available water TAW. No weather
forecast, no data after the analysis date, no equipment or cost values.

By the state of the date for the crop (`season.season_status`):
- no crop: not applicable, with the reason;
- outside the season: the fixed off-season sentence with the season dates;
- current water status not assessed (no weather): applicable, not decided;
- dormant winter crop: not justified, because the deficit level describes the
  soil water store and not the needs of the crop;
- in the season: justified when the deficit level reaches the level in
  `irrigation_params`; then a range of net amounts, see `amount_range`.

Pure and deterministic. The rules and their sources are in `irrigation_params`.
"""

import math
from dataclasses import dataclass
from typing import Literal

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import critical_period_on
from app.contracts.causes import Irrigation
from app.contracts.common import Scalar
from app.contracts.report import TraceEntry
from app.engine import irrigation_texts as texts
from app.engine.assessment import WaterAssessment
from app.engine.irrigation_params import (
    DEFAULT_IRRIGATION_PARAMS,
    M3_PER_HA_PER_MM,
    IrrigationParams,
)
from app.engine.params import DEFICIT_LEVEL_LABELS
from app.engine.season import SeasonStatus, season_status
from app.engine.season_texts import off_season_irrigation

RULE_ID = "irrigation.need"

IrrigationKind = Literal[
    "no_crop", "out_of_season", "not_assessed", "dormant", "not_justified", "justified"
]

_RESULTS: dict[IrrigationKind, str] = {
    "no_crop": "nie dotyczy: Pole bez uprawy",
    "out_of_season": "nie dotyczy: Data analizy poza Sezonem uprawy",
    "not_assessed": "nie oceniono: brak danych pogodowych",
    "dormant": "nie jest zasadne: uprawa w spoczynku",
    "not_justified": "nie jest zasadne: brak niedoboru",
}


@dataclass(frozen=True)
class IrrigationAmount:
    """Range of the net irrigation amount; the rounded ends lie inside the exact ones."""

    min_mm: float
    max_mm: float
    # Ends before rounding: Dr - RAW and Dr.
    exact_min_mm: float
    exact_max_mm: float

    @property
    def mm(self) -> tuple[float, float]:
        return (self.min_mm, self.max_mm)

    @property
    def m3_ha(self) -> tuple[float, float]:
        return (self.min_mm * M3_PER_HA_PER_MM, self.max_mm * M3_PER_HA_PER_MM)


@dataclass(frozen=True)
class IrrigationOutcome:
    kind: IrrigationKind
    # The part of the Report, ready to show.
    section: Irrigation
    # None unless irrigation is justified.
    amount: IrrigationAmount | None
    trace: TraceEntry


def amount_range(depletion_mm: float, raw_mm: float, step_mm: float) -> IrrigationAmount:
    """From the amount that ends the stress (Dr - RAW) to the one that refills the zone (Dr).

    The lower end is rounded up and the upper end down to `step_mm`, so the
    rounded range never leaves the exact one; a range narrower than one step
    collapses to its upper end, and one below a single step is left unrounded.
    """
    low, high = max(0.0, depletion_mm - raw_mm), depletion_mm
    # Rounding to 6 places first keeps float noise from moving a whole step.
    upper = math.floor(round(high / step_mm, 6)) * step_mm
    lower = min(math.ceil(round(low / step_mm, 6)) * step_mm, upper)
    if upper <= 0:
        lower, upper = low, high
    return IrrigationAmount(min_mm=lower, max_mm=upper, exact_min_mm=low, exact_max_mm=high)


def _section(
    applicable: bool,
    text: str,
    justified: bool | None = None,
    amount: IrrigationAmount | None = None,
    timing: str | None = None,
    reason_if_none: str | None = None,
) -> Irrigation:
    return Irrigation(
        applicable=applicable,
        text=text,
        justified=justified,
        amount_mm=None if amount is None else amount.mm,
        amount_m3_ha=None if amount is None else amount.m3_ha,
        timing=timing,
        reason_if_none=reason_if_none,
    )


def _trace(
    kind: IrrigationKind,
    assessment: WaterAssessment,
    status: SeasonStatus,
    params: IrrigationParams,
    amount: IrrigationAmount | None,
    in_critical_period: bool,
) -> TraceEntry:
    verdict, zone = assessment.current_status, assessment.root_zone
    details = verdict.details()
    values: dict[str, Scalar] = {
        "season_state": status.state,
        "state_date": None if verdict.state_date is None else verdict.state_date.isoformat(),
        "deficit_level": verdict.deficit_level,
        "depletion_mm": details["depletion_mm"],
        "readily_available_water_mm": details["readily_available_water_mm"],
        "total_available_water_mm": details["total_available_water_mm"],
        "capacity_source": zone.capacity_source,
        "in_critical_period": in_critical_period,
        "justified": None if kind in ("no_crop", "out_of_season", "not_assessed") else (
            kind == "justified"
        ),
        "amount_min_mm": None if amount is None else amount.min_mm,
        "amount_max_mm": None if amount is None else amount.max_mm,
    }
    if amount is None:
        result = _RESULTS[kind]
    else:
        result = (
            f"zasadne: od {texts.number(amount.min_mm)} do {texts.number(amount.max_mm)} mm"
        )
    return TraceEntry(
        rule_id=RULE_ID,
        condition=(
            "nawadnianie zasadne, gdy Data analizy jest w Sezonie uprawy poza spoczynkiem, "
            "a Stopień niedoboru Bieżącej sytuacji wodnej to co najmniej "
            f"{DEFICIT_LEVEL_LABELS[params.justified_from_level]}; zakres od ilości kończącej "
            "brak wody (wyczerpanie strefy korzeniowej ponad wodę łatwo dostępną) do ilości "
            "uzupełniającej strefę korzeniową do pełna (całe wyczerpanie), zaokrąglony do "
            f"{texts.number(params.amount_step_mm)} mm do wewnątrz; 1 mm = 10 m³ na hektar; "
            "wyłącznie stan na Datę analizy, bez prognozy pogody"
        ),
        values=values,
        result=result,
    )


def assess_irrigation(
    assessment: WaterAssessment,
    crop: CatalogCrop,
    status: SeasonStatus | None = None,
    params: IrrigationParams = DEFAULT_IRRIGATION_PARAMS,
) -> IrrigationOutcome:
    """The irrigation part for the crop on the analysis date of the assessment.

    `status` is the season state of that date; it is derived when not given.
    """
    if status is None:
        status = season_status(crop, assessment.analysis_date)
    verdict, zone = assessment.current_status, assessment.root_zone
    critical = critical_period_on(crop, assessment.analysis_date)
    amount: IrrigationAmount | None = None

    if status.state == "no_crop":
        kind: IrrigationKind = "no_crop"
        section = _section(False, texts.NO_CROP, reason_if_none=texts.NO_CROP)
    elif status.state == "out_of_season":
        kind = "out_of_season"
        section = off_season_irrigation(crop, status)
    elif not verdict.assessed:
        kind = "not_assessed"
        section = _section(True, texts.NO_WEATHER, reason_if_none=texts.NO_WEATHER)
    elif status.state == "dormant":
        kind = "dormant"
        section = _section(
            True,
            texts.dormant_text(verdict, zone, status.dormancy),
            justified=False,
            timing=texts.dormant_timing(status.dormancy),
            reason_if_none=texts.dormant_reason(verdict, status.dormancy),
        )
    elif verdict.deficit_level < params.justified_from_level:
        kind = "not_justified"
        section = _section(
            True,
            texts.not_justified_text(verdict, zone),
            justified=False,
            timing=texts.not_justified_timing(verdict, params.justified_from_level),
            reason_if_none=texts.not_justified_reason(verdict),
        )
    else:
        kind = "justified"
        amount = amount_range(
            verdict.depletion_mm, verdict.readily_available_water_mm, params.amount_step_mm
        )
        section = _section(
            True,
            texts.justified_text(verdict, zone, amount.mm, amount.m3_ha),
            justified=True,
            amount=amount,
            timing=texts.justified_timing(verdict, critical),
        )
    trace = _trace(kind, assessment, status, params, amount, critical is not None)
    return IrrigationOutcome(kind=kind, section=section, amount=amount, trace=trace)
