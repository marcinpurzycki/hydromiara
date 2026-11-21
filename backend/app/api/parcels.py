"""Parcel lookup: by identifier, by number with region name, by map point."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.errors import ApiError, error_responses
from app.contracts.parcels import ParcelDetail, ParcelMatch, ParcelSearchResponse
from app.contracts.source_data import ParcelData
from app.sources.parcel_query import ParcelQueryError, in_poland
from app.sources.parcels import ParcelSource, ParcelSourceError, get_parcel_source

router = APIRouter(prefix="/parcels", tags=["parcels"])

Source = Annotated[ParcelSource, Depends(get_parcel_source)]

_MATCH_FIELDS = {"parcel_id", "number", "region", "commune", "county", "voivodeship"}


def _match(parcel: ParcelData) -> ParcelMatch:
    return ParcelMatch.model_validate(parcel.model_dump(include=_MATCH_FIELDS))


def _detail(parcel: ParcelData) -> ParcelDetail:
    return ParcelDetail.model_validate(parcel.model_dump(include=_MATCH_FIELDS | {"geometry"}))


def _unavailable() -> ApiError:
    return ApiError(
        503,
        "parcel_source_unavailable",
        "Usługa lokalizacji działek (ULDK) nie odpowiada. Spróbuj ponownie za chwilę.",
    )


@router.get(
    "/search",
    response_model=ParcelSearchResponse,
    responses=error_responses(422, 503),
    summary="Wyszukanie po Identyfikatorze albo Numerze działki z obrębem",
)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=120)], source: Source
) -> ParcelSearchResponse:
    try:
        parcels = await source.search(q)
    except ParcelQueryError:
        raise ApiError(
            422,
            "invalid_parcel_query",
            "Podaj identyfikator działki (np. 040704_2.0020.34/2) albo numer działki "
            "z nazwą obrębu (np. Krusza Podlotowa 34/2).",
        ) from None
    except ParcelSourceError:
        raise _unavailable() from None
    return ParcelSearchResponse(matches=[_match(parcel) for parcel in parcels])


@router.get(
    "/at",
    response_model=ParcelSearchResponse,
    responses=error_responses(422, 503),
    summary="Działka w punkcie mapy",
)
async def at(
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    source: Source,
) -> ParcelSearchResponse:
    if not in_poland(lon, lat):
        raise ApiError(
            422, "point_outside_poland", "Wskazany punkt leży poza Polską. Wskaż działkę w Polsce."
        )
    try:
        parcel = await source.at(lon, lat)
    except ParcelSourceError:
        raise _unavailable() from None
    return ParcelSearchResponse(matches=[_detail(parcel)] if parcel else [])


# Parcel identifiers contain a slash, hence the path converter. Declared last
# so that it does not capture /search and /at.
@router.get(
    "/{parcel_id:path}",
    response_model=ParcelDetail,
    responses=error_responses(404, 503),
    summary="Geometria działki do podglądu",
)
async def detail(parcel_id: str, source: Source) -> ParcelDetail:
    try:
        parcel = await source.by_id(parcel_id)
    except ParcelSourceError:
        raise _unavailable() from None
    if parcel is None:
        raise ApiError(404, "parcel_not_found", "Działka o takim identyfikatorze nie istnieje.")
    return _detail(parcel)
