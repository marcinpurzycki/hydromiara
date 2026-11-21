"""Parcel lookup responses."""

from pydantic import Field

from app.contracts.common import ContractModel, GeoJsonGeometry


class ParcelMatch(ContractModel):
    parcel_id: str = Field(description="Pełny Identyfikator działki, np. 040704_2.0020.34/2.")
    number: str = Field(description="Numer działki w obrębie, np. 34/2.")
    region: str = Field(description="Obręb ewidencyjny.")
    commune: str
    county: str
    voivodeship: str
    geometry: GeoJsonGeometry | None = None


class ParcelSearchResponse(ContractModel):
    """Zero, one or many matches; the user picks when there are many."""

    matches: list[ParcelMatch]


class ParcelDetail(ParcelMatch):
    geometry: GeoJsonGeometry
