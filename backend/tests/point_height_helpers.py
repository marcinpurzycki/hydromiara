"""Helpers for the point height tests: a stand-in service and metric grids.

`PointService` answers like the height service: `x y h` rows in the order of
the request, x being the northing. `metric_grid` builds an elevation grid in
PL-1992 over the same ground surface the geographic helper uses, so results
on both kinds of grid can be compared.
"""

import asyncio
import math
from collections.abc import Callable

import httpx
from pyproj import Transformer

from app.contracts.source_data import TerrainData
from app.engine.terrain_grid import metres_per_degree
from tests.terrain_helpers import LAT, LON, Surface

# Height of a point from its northing and easting; None leaves the field out.
HeightAt = Callable[[int, int], float | None]

_TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
_TO_GEOGRAPHIC = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)


def tilted(northing0: int, easting0: int, per_north: float = 0.02, per_east: float = 0.0) -> HeightAt:
    return lambda n, e: round(100.0 + per_north * (n - northing0) + per_east * (e - easting0), 1)


class PointService(httpx.AsyncBaseTransport):
    """Answers point lists; `faults` maps a request number (from 0) to a faulty answer."""

    def __init__(self, height: HeightAt, faults: dict[int, str] | None = None, delay_s: float = 0.0):
        self._height, self._faults, self._delay_s = height, faults or {}, delay_s
        self.requests: list[httpx.Request] = []
        self.batches: list[list[tuple[int, int]]] = []
        self.limit = 1000

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        number = len(self.requests)
        self.requests.append(request)
        await asyncio.sleep(self._delay_s)
        points = [tuple(int(v) for v in pair.split()) for pair in request.url.params["list"].split(",")]
        self.batches.append(points)
        fault = self._faults.get(number)
        if fault == "error":
            return httpx.Response(503, text="Service Unavailable")
        rows = []
        for index, (northing, easting) in enumerate(points):
            height = 0.0 if fault == "zeros" else self._height(northing, easting)
            if height is None or index >= self.limit:
                rows.append(f"{northing} {easting}")
            else:
                rows.append(f"{northing} {easting} {height:.1f}")
        return httpx.Response(200, text=",".join(rows))


def metric_grid(
    surface: Surface, *, lon: float = LON, lat: float = LAT, step: int = 5, half: int = 30,
    digits: int | None = 1,
) -> TerrainData:  # fmt: skip
    """Grid in PL-1992 around the point; the surface is given in true east and north metres."""
    east0, north0 = (round(v) for v in _TO_METRIC.transform(lon, lat))
    per_lon, per_lat = metres_per_degree(lat)
    rows = []
    for row in range(2 * half + 1):
        values = []
        for col in range(2 * half + 1):
            east, north = east0 + (col - half) * step, north0 + (half - row) * step
            point_lon, point_lat = _TO_GEOGRAPHIC.transform(east, north)
            value = surface((point_lon - lon) * per_lon, (point_lat - lat) * per_lat)
            values.append(value if value is None or digits is None else round(value, digits))
        rows.append(values)
    west, top = east0 - half * step - step / 2, north0 + half * step + step / 2
    return TerrainData(
        resolution_m=float(step), crs="EPSG:2180",
        transform=(float(step), 0.0, west, 0.0, -float(step), top), elevations_m=rows,
    )  # fmt: skip


def expected_convergence_deg(lon: float, lat: float) -> float:
    """Textbook meridian convergence of PL-1992 (central meridian 19 E)."""
    return (lon - 19.0) * math.sin(math.radians(lat))
