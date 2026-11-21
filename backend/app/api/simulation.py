"""Simulation: crop ranking and year-by-year comparison. Placeholder implementation."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.errors import ApiError, error_responses
from app.api.reports import require_ready
from app.contracts.simulation import (
    CompareResponse,
    CompareYear,
    CropSusceptibility,
    RankingResponse,
)
from app.mock import data

router = APIRouter(prefix="/reports/{report_id}/simulation", tags=["simulation"])


def _public(crop: CropSusceptibility) -> CropSusceptibility:
    return CropSusceptibility.model_validate(crop.model_dump(exclude={"deficit_in"}))


@router.get(
    "/ranking",
    response_model=RankingResponse,
    responses=error_responses(404, 425),
    summary="Ranking upraw: trzy najmniej narażone na niedobór wody",
)
def ranking(report_id: str) -> RankingResponse:
    require_ready(report_id)
    simulation = data.catalog().simulation
    others = sorted(simulation.others, key=lambda crop: crop.deficit_years)
    return RankingResponse(
        current=simulation.current,
        top=[_public(crop) for crop in others[:3]],
        limitations=simulation.limitations,
    )


@router.get(
    "/compare",
    response_model=CompareResponse,
    responses=error_responses(404, 422, 425),
    summary="Porównanie bieżącej Uprawy z jedną wybraną, rok po roku",
)
def compare(
    report_id: str, crop_id: Annotated[str, Query(min_length=1, max_length=64)]
) -> CompareResponse:
    require_ready(report_id)
    simulation = data.catalog().simulation
    other = next((crop for crop in simulation.others if crop.crop_id == crop_id), None)
    if other is None:
        raise ApiError(422, "unknown_crop", "Nieznana uprawa. Wybierz uprawę z listy.")
    report_years = data.report_for(report_id).multiyear_susceptibility.years
    years = [
        CompareYear(
            year=entry.year,
            current_deficit=entry.deficit,
            other_deficit=entry.year in other.deficit_in,
            partial=entry.partial,
        )
        for entry in report_years
    ]
    return CompareResponse(current=simulation.current, other=_public(other), years=years)
