"""Report parts: season, the two verdicts, historical course, consistency check."""

from datetime import date
from typing import Literal

from pydantic import Field

from app.contracts.common import Confidence, ContractModel, DeficitLevel, Scalar


class CropRef(ContractModel):
    id: str
    name: str


class DateRange(ContractModel):
    start: date
    end: date


class Season(ContractModel):
    in_season: bool
    last_season: DateRange | None
    note: str | None = None


class CurrentStatus(ContractModel):
    deficit_level: DeficitLevel
    label: str
    reason: str
    confidence: Confidence
    details: dict[str, Scalar] = Field(description="Liczby z jednostką w nazwie klucza.")


class MultiyearYear(ContractModel):
    year: int
    deficit: bool
    partial: bool = Field(description="Rok Daty analizy liczony tylko do tej daty.")
    values: dict[str, Scalar]


class MultiyearSusceptibility(ContractModel):
    deficit_years: int = Field(ge=0)
    total_years: int = Field(ge=0)
    deficit_level: DeficitLevel
    typical_period: str | None
    confidence: Confidence
    years: list[MultiyearYear]
    history_assumption: str


class HistoricalYear(ContractModel):
    year: int
    crop: CropRef
    deficit: bool
    satellite_note: str | None = None


class HistoricalCourse(ContractModel):
    years: list[HistoricalYear]
    comparison_sentence: str


class ConsistencyItem(ContractModel):
    source: str
    period: str
    value: str
    meaning: str


class ConsistencyCheck(ContractModel):
    result: Literal["zgodne", "rozbieżne", "brak danych"]
    sentence: str
    items: list[ConsistencyItem]
