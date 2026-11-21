"""Starting an analysis, tracking its progress and supplying crop history."""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator
from typing_extensions import Self

from app.contracts.common import ContractModel

SourceId = Literal["weather", "satellite", "soil", "hydro", "terrain"]


class AnalysisRequest(ContractModel):
    parcel_id: str = Field(min_length=1, max_length=64)
    crop_id: str = Field(min_length=1, max_length=64)
    analysis_date: date


class AnalysisStarted(ContractModel):
    report_id: str


class SourceProgress(ContractModel):
    id: SourceId
    state: Literal["wait", "run", "done", "missing"]
    note: str | None = None


class AnalysisStatus(ContractModel):
    state: Literal["running", "done", "failed"]
    sources: list[SourceProgress]


class CropHistory(ContractModel):
    """Either a crop per year or one crop every year, never both."""

    years: dict[int, str] | None = Field(
        default=None, description="Rok → identyfikator Uprawy; lata niepodane są pomijane."
    )
    same_every_year: bool | None = None

    @model_validator(mode="after")
    def exactly_one_form(self) -> Self:
        if (self.years is None) == (self.same_every_year is None):
            raise ValueError("provide either years or same_every_year")
        return self


class DeriveRequest(ContractModel):
    crop_history: CropHistory


class DerivedReport(ContractModel):
    report_id: str


class CriticalPeriodStarted(ContractModel):
    report_id: str
    analysis_date: date
