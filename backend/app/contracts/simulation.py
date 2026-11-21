"""Simulation: susceptibility of other crops on the same parcel."""

from app.contracts.common import ContractModel, DeficitLevel
from app.contracts.report import Limitation


class CropSusceptibility(ContractModel):
    crop_id: str
    name: str
    deficit_years: int
    total_years: int
    deficit_level: DeficitLevel


class RankingResponse(ContractModel):
    current: CropSusceptibility
    top: list[CropSusceptibility]
    limitations: list[Limitation]


class CompareYear(ContractModel):
    year: int
    current_deficit: bool
    other_deficit: bool
    partial: bool


class CompareResponse(ContractModel):
    current: CropSusceptibility
    other: CropSusceptibility
    years: list[CompareYear]
