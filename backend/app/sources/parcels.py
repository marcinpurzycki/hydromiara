"""Parcels from the ULDK service of GUGiK (https://uldk.gugik.gov.pl/).

The service answers in plain text: the first line is a status (`0` on
success; for GetParcelByIdOrNr the number of parcels found; `-1 ...` when
nothing was found), followed by one line per parcel with fields separated
by `|`. Geometry is returned as EWKT (`SRID=4326;POLYGON(...)`).
"""

import time
from datetime import UTC, datetime

import httpx
import shapely
from pyproj import Transformer
from shapely.geometry import mapping

from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import ParcelData, SourceOutcome
from app.sources.parcel_query import in_poland, is_parcel_id, normalize_query

ULDK_URL = "https://uldk.gugik.gov.pl/"
SOURCE_NAME = "ULDK GUGiK"
USER_AGENT = "hydro-analysis/0.1"

_FIELDS = ("id", "voivodeship", "county", "commune", "region", "parcel", "geom_wkt")
_NOT_FOUND = "-1"

# Lookups by identifier or point answer in well under a second; a search by
# region name is forwarded to every county that has a region of that name.
TIMEOUT_S = 10.0
SEARCH_TIMEOUT_S = 30.0

# Area is measured in the national projected system PUWG 1992 (metres).
_TO_PUWG1992 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)


class ParcelSourceError(Exception):
    """The parcel service did not answer or answered with something unreadable."""


def _parse_row(line: str) -> ParcelData | None:
    fields = line.split("|")
    if len(fields) != len(_FIELDS):
        return None
    parcel_id, voivodeship, county, commune, region, number, ewkt = (f.strip() for f in fields)
    try:
        geometry = shapely.from_wkt(ewkt.split(";")[-1])
    except shapely.errors.ShapelyError:
        return None
    if not parcel_id or geometry is None or geometry.is_empty:
        return None
    projected = shapely.transform(geometry, _TO_PUWG1992.transform, interleaved=False)
    if projected.area <= 0:
        return None
    centroid = geometry.centroid
    return ParcelData(
        parcel_id=parcel_id,
        number=number,
        region=region,
        commune=commune,
        county=county,
        voivodeship=voivodeship,
        geometry=GeoJsonGeometry.model_validate(mapping(geometry)),
        area_ha=round(projected.area / 10_000, 4),
        centroid_lon=centroid.x,
        centroid_lat=centroid.y,
    )


def parse_response(text: str) -> list[ParcelData]:
    """Parcels from one service answer; an empty list when nothing was found."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ParcelSourceError("empty answer")
    status = lines[0].split()[0]
    if status == _NOT_FOUND:
        return []
    if not status.isdigit():
        raise ParcelSourceError(f"unexpected status line: {lines[0][:80]!r}")

    parcels: dict[str, ParcelData] = {}
    for line in lines[1:]:
        parcel = _parse_row(line)
        if parcel is not None:
            parcels.setdefault(parcel.parcel_id, parcel)
    if not parcels:
        raise ParcelSourceError("success status without a readable parcel")
    return list(parcels.values())


class ParcelSource:
    """Three lookups: by identifier, by text query and by map point."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _request(self, params: dict[str, str], timeout: float) -> list[ParcelData]:
        query = {**params, "result": ",".join(_FIELDS), "srid": "4326"}
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(ULDK_URL, params=query)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ParcelSourceError(type(exc).__name__) from exc
        return parse_response(response.text)

    async def by_id(self, parcel_id: str) -> ParcelData | None:
        """The parcel with this identifier, or None when it does not exist."""
        parcel_id = parcel_id.strip()
        if not is_parcel_id(parcel_id):
            return None
        found = await self._request({"request": "GetParcelById", "id": parcel_id}, TIMEOUT_S)
        return found[0] if found else None

    async def search(self, text: str) -> list[ParcelData]:
        """Zero, one or many parcels for an identifier or a number with a region name.

        Raises ParcelQueryError when the text is in neither form.
        """
        query = normalize_query(text)
        return await self._request(
            {"request": "GetParcelByIdOrNr", "id": query}, SEARCH_TIMEOUT_S
        )

    async def at(self, lon: float, lat: float) -> ParcelData | None:
        """The parcel containing the point, or None (also for points outside Poland)."""
        if not in_poland(lon, lat):
            return None
        found = await self._request(
            {"request": "GetParcelByXY", "xy": f"{lon},{lat},4326"}, TIMEOUT_S
        )
        return found[0] if found else None

    async def fetch(self, parcel_id: str) -> tuple[ParcelData | None, SourceOutcome]:
        """Parcel for an analysis together with the record of how it was obtained."""
        started = time.monotonic()
        parcel, message = None, None
        try:
            parcel = await self.by_id(parcel_id)
            if parcel is None:
                message = "Działka o takim identyfikatorze nie istnieje."
        except ParcelSourceError:
            message = "Usługa lokalizacji działek nie odpowiedziała."
        fetched_at = datetime.now(UTC)
        outcome = SourceOutcome(
            topic="parcel",
            source_name=SOURCE_NAME if parcel else None,
            chain_step=1 if parcel else None,
            ok=parcel is not None,
            duration_s=round(time.monotonic() - started, 3),
            data_date=fetched_at.date().isoformat() if parcel else None,
            fetched_at=fetched_at,
            message=message,
        )
        return parcel, outcome


_default_source = ParcelSource()


def get_parcel_source() -> ParcelSource:
    """Dependency for the API routes; tests replace it with a recorded source."""
    return _default_source
