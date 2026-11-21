"""The Report: immutable result of one analysis."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.contracts.causes import Cause, Irrigation, RetentionSite
from app.contracts.common import ContractModel, GeoJsonGeometry, Scalar
from app.contracts.verdicts import (
    ConsistencyCheck,
    CropRef,
    CurrentStatus,
    HistoricalCourse,
    MultiyearSusceptibility,
    Season,
)


class ReportParcel(ContractModel):
    parcel_id: str
    number: str
    region: str
    commune: str
    county: str
    voivodeship: str
    area_ha: float


class ReportMeta(ContractModel):
    report_id: str
    created_at: datetime
    parcel: ReportParcel
    crop: CropRef
    analysis_date: date
    derived_from: str | None = Field(description="Raport źródłowy, gdy ten powstał z innego.")
    changed_from_date: date | None = Field(
        description="Pierwotna Data analizy, gdy Raport dotyczy Okresu krytycznego."
    )


class Summary(ContractModel):
    text: str
    source: Literal["llm", "template"]


class ReportSource(ContractModel):
    topic: str
    name: str
    license: str
    mode: Literal["na żywo", "plik lokalny"]
    data_date: str | None = Field(description="Dzień lub zakres dat, których dotyczą dane.")
    fetched_at: datetime | None
    chain_step: int = Field(ge=1, description="Ogniwo Łańcucha zamienników; 1 = podstawowe.")
    missing: bool


class Limitation(ContractModel):
    text: str
    affects: Literal["current", "multiyear", "recommendations", "all"]
    permanent: bool


class DownhillDirection(ContractModel):
    label: str
    azimuth_deg: float = Field(ge=0, lt=360)


class WaterObject(ContractModel):
    kind: str
    name: str | None
    geometry: GeoJsonGeometry


class ReportMap(ContractModel):
    parcel_geometry: GeoJsonGeometry
    downhill_direction: DownhillDirection | None
    retention_sites: list[RetentionSite]
    water_objects: list[WaterObject]


class TraceEntry(ContractModel):
    """One step of the decision trace."""

    rule_id: str
    condition: str
    values: dict[str, Scalar]
    result: str


class Report(ContractModel):
    meta: ReportMeta
    headline: str
    summary: Summary
    season: Season
    current_status: CurrentStatus
    multiyear_susceptibility: MultiyearSusceptibility
    historical_course: HistoricalCourse | None
    causes: list[Cause]
    irrigation: Irrigation
    consistency_check: ConsistencyCheck
    sources: list[ReportSource]
    limitations: list[Limitation]
    map: ReportMap
    trace: list[TraceEntry]
