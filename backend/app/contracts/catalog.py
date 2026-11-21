"""Crop list and ready-made examples."""

from datetime import date
from typing import Literal

from pydantic import Field

from app.contracts.common import ContractModel


class MonthDay(ContractModel):
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)


class YearlyPeriod(ContractModel):
    """Period repeating every year; it may cross the turn of the year."""

    start: MonthDay
    end: MonthDay


class Crop(ContractModel):
    id: str
    name: str = Field(description="Nazwa w mianowniku, np. Pszenica ozima.")
    name_genitive: str = Field(description="Nazwa w dopełniaczu, np. pszenicy ozimej.")
    tile: bool = Field(description="Czy Uprawa jest pokazywana jako kafel.")
    season: YearlyPeriod | None = Field(description="Sezon uprawy; null dla Pola bez uprawy.")
    critical_period: YearlyPeriod | None


class Example(ContractModel):
    label: str
    parcel_id: str
    crop_id: str
    analysis_date: date
    kind: Literal["deficit", "no_deficit"]
