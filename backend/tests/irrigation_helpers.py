"""Helpers for the irrigation tests: an assessment with a chosen root zone depletion."""

from datetime import date, timedelta

from app.catalog.crop_model import CatalogCrop
from app.engine.assessment import WaterAssessment
from app.engine.balance import DayBalance, WaterBalance
from app.engine.root_zone import RootZone
from app.engine.susceptibility import multiyear_susceptibility
from app.engine.verdicts import current_status
from tests.engine_helpers import SIMPLE_ZONE, WHEAT


def assessment_with(
    depletion_mm: float | None,
    day: date,
    crop: CatalogCrop = WHEAT,
    zone: RootZone = SIMPLE_ZONE,
    days: int = 3,
    later_days: int = 0,
) -> WaterAssessment:
    """The last `days` days up to `day` end with the given depletion; None = no weather.

    `later_days` adds records after the analysis date that a balance never holds;
    they must not change anything.
    """
    records = []
    if depletion_mm is not None:
        for offset in range(-(days - 1), later_days + 1):
            value = depletion_mm if offset <= 0 else 0.0
            records.append(
                DayBalance(
                    date=day + timedelta(days=offset),
                    precipitation_mm=0.0,
                    et0_mm=3.0,
                    kc=1.0,
                    ks=zone.stress_coefficient(value),
                    etc_mm=3.0,
                    drainage_mm=0.0,
                    depletion_mm=value,
                    stressed=zone.is_stressed(value),
                    complete=True,
                )
            )
    kept = tuple(record for record in records if record.date <= day)
    balance = WaterBalance(
        analysis_date=day, root_zone=zone, days=kept, incomplete_days=0, missing_dates=0
    )
    return WaterAssessment(
        crop_id=crop.id,
        analysis_date=day,
        root_zone=zone,
        balance=balance,
        current_status=current_status(balance),
        multiyear_susceptibility=multiyear_susceptibility(balance, crop),
    )
