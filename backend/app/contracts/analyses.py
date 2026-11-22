"""Starting an analysis, tracking its progress and supplying crop history."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator
from typing_extensions import Self

from app.contracts.common import ContractModel

SourceId = Literal["weather", "satellite", "soil", "hydro", "terrain"]

# Form of a crop identifier as sent by a client: lower-case words joined by
# underscores, like every identifier of the crop list.
CropId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]

# Bounds of a crop history as sent by a client: far more years than a
# multi-year window has, and calendar years only.
MAX_HISTORY_YEARS = 32
HistoryYear = Annotated[int, Field(ge=1900, le=2200)]


class AnalysisRequest(ContractModel):
    parcel_id: str = Field(min_length=1, max_length=64)
    crop_id: CropId
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

    years: dict[HistoryYear, CropId] | None = Field(
        default=None,
        max_length=MAX_HISTORY_YEARS,
        description="Rok → identyfikator Uprawy; lata niepodane są pomijane.",
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
