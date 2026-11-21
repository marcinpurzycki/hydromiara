"""Parcel lookup. Placeholder: knows exactly one parcel."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.errors import ApiError, error_responses
from app.contracts.parcels import ParcelDetail, ParcelMatch, ParcelSearchResponse
from app.mock import data

router = APIRouter(prefix="/parcels", tags=["parcels"])


def _without_geometry(parcel: ParcelDetail) -> ParcelMatch:
    return ParcelMatch.model_validate(parcel.model_dump(exclude={"geometry"}))


@router.get(
    "/search",
    response_model=ParcelSearchResponse,
    responses=error_responses(422),
    summary="Wyszukanie po Identyfikatorze albo Numerze działki z obrębem",
)
def search(q: Annotated[str, Query(min_length=1, max_length=120)]) -> ParcelSearchResponse:
    parcel = data.catalog().parcel
    query = q.strip().lower()
    known = parcel.parcel_id.lower() in query or parcel.number in query
    return ParcelSearchResponse(matches=[_without_geometry(parcel)] if known else [])


@router.get(
    "/at",
    response_model=ParcelSearchResponse,
    responses=error_responses(422),
    summary="Działka w punkcie mapy",
)
def at(
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
) -> ParcelSearchResponse:
    return ParcelSearchResponse(matches=[data.catalog().parcel])


# Parcel identifiers contain a slash, hence the path converter. Declared last
# so that it does not capture /search and /at.
@router.get(
    "/{parcel_id:path}",
    response_model=ParcelDetail,
    responses=error_responses(404),
    summary="Geometria działki do podglądu",
)
def detail(parcel_id: str) -> ParcelDetail:
    parcel = data.catalog().parcel
    if parcel_id != parcel.parcel_id:
        raise ApiError(404, "parcel_not_found", "Działka o takim identyfikatorze nie istnieje.")
    return parcel
