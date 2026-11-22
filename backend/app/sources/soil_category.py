"""Soil drought susceptibility category of a parcel from the IUNG-PIB map service.

One `GetFeatureInfo` request returns the value of one 5 m map cell. The
parcel is read at a lattice of points, a few requests at a time; the answer
is the share of every map value among the points. Only point coordinates
leave the application.
"""

import asyncio
from collections import Counter
from collections.abc import Sequence

import httpx

from app.contracts.source_data import DroughtCategoryShare, UnclassifiedArea
from app.sources import soil_params as params
from app.sources.chain import LinkFailed
from app.sources.soil_points import Point

UNREADABLE = "mapa kategorii gleb odpowiedziała nieczytelnie"
UNAVAILABLE = "mapa kategorii gleb nie odpowiedziała"

CategoryShares = tuple[list[DroughtCategoryShare], list[UnclassifiedArea]]


def point_query(lon: float, lat: float) -> dict[str, str]:
    """Query of one map cell: a 3 x 3 pixel window with the point in its centre."""
    half = params.CATEGORY_WINDOW_HALF_DEG
    return {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": params.CATEGORY_LAYER,
        "QUERY_LAYERS": params.CATEGORY_LAYER,
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": f"{lon - half:.6f},{lat - half:.6f},{lon + half:.6f},{lat + half:.6f}",
        "WIDTH": "3",
        "HEIGHT": "3",
        "X": "1",
        "Y": "1",
        "INFO_FORMAT": "application/json",
    }


def parse_map_value(payload: object) -> int:
    """Value of the map cell from one answer; raises LinkFailed when unreadable.

    An answer without any feature means the point lies outside the map.
    """
    try:
        features = payload["features"]
        if not features:
            return params.CODE_OUTSIDE_MAP
        value = features[0]["properties"][params.CATEGORY_PROPERTY]
        if isinstance(value, bool) or int(value) != value:
            raise ValueError("map value is not an integer")
        return int(value)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LinkFailed(UNREADABLE) from exc


def shares(values: Sequence[int]) -> CategoryShares:
    """Shares of the categories and of the other map values, largest first."""
    if not values:
        return [], []
    counts = Counter(values)

    def share(count: int) -> float:
        return round(100.0 * count / len(values), 1)

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    categories = [
        DroughtCategoryShare(category=value, share_pct=share(count))
        for value, count in ordered
        if value in params.CATEGORY_VALUES
    ]
    other = [
        UnclassifiedArea(code=value, share_pct=share(count))
        for value, count in ordered
        if value not in params.CATEGORY_VALUES
    ]
    return categories, other


class CategoryMap:
    """Reads the category map at given points."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def read(self, points: Sequence[Point]) -> CategoryShares:
        """Shares of the map values among the points; raises LinkFailed."""
        gate = asyncio.Semaphore(params.CATEGORY_CONCURRENCY)

        async def one(client: httpx.AsyncClient, point: Point) -> int:
            async with gate:
                response = await client.get(params.CATEGORY_URL, params=point_query(*point))
            response.raise_for_status()
            return parse_map_value(response.json())

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=params.CATEGORY_TIMEOUT_S,
                headers={"User-Agent": params.USER_AGENT},
            ) as client:
                values = await asyncio.gather(*(one(client, point) for point in points))
        except httpx.HTTPError as exc:
            raise LinkFailed(UNAVAILABLE) from exc
        except ValueError as exc:  # the answer is not JSON
            raise LinkFailed(UNREADABLE) from exc
        return shares(values)
