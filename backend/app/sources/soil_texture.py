"""Soil texture and organic carbon of a point from the SoilGrids coverage service.

Every property and depth is one small GeoTIFF window around the point, asked
in the projection of the maps; the value of the cell containing the point is
used. All layers are asked at the same time. Only the point coordinates
leave the application.
"""

import asyncio

import httpx
from pyproj import Transformer
from rasterio.errors import RasterioError
from rasterio.io import MemoryFile

from app.contracts.source_data import SoilLayer
from app.sources import soil_params as params
from app.sources.chain import LinkFailed

UNREADABLE = "globalna mapa gleb odpowiedziała nieczytelnie"
UNAVAILABLE = "globalna mapa gleb nie odpowiedziała"
NO_DATA = "globalna mapa gleb nie ma wartości dla tego miejsca (np. woda albo zabudowa)"

_TEXTURE_FIELDS = ("sand_pct", "silt_pct", "clay_pct")


def map_coordinates(lon: float, lat: float) -> tuple[float, float]:
    """The point in the projection of the maps, metres."""
    transformer = Transformer.from_crs("EPSG:4326", params.HOMOLOSINE_PROJ, always_xy=True)
    return transformer.transform(lon, lat)


def coverage_query(name: str, depth: str, x: float, y: float) -> dict[str, str | list[str]]:
    """Query of one property at one depth: a window around the map point."""
    half = params.TEXTURE_WINDOW_HALF_M
    return {
        "map": f"/map/{name}.map",
        "SERVICE": "WCS",
        "VERSION": "2.0.1",
        "REQUEST": "GetCoverage",
        "COVERAGEID": f"{name}_{depth}_mean",
        "FORMAT": "image/tiff",
        "SUBSET": [f"X({x - half:.1f},{x + half:.1f})", f"Y({y - half:.1f},{y + half:.1f})"],
        "SUBSETTINGCRS": params.HOMOLOSINE_URI,
        "OUTPUTCRS": params.HOMOLOSINE_URI,
    }


def cell_value(content: bytes, x: float, y: float) -> int:
    """Value of the cell that contains the map point; raises LinkFailed when unreadable."""
    try:
        with MemoryFile(content) as memory, memory.open() as dataset:
            row, col = dataset.index(x, y)
            band = dataset.read(1)
            if not (0 <= row < band.shape[0] and 0 <= col < band.shape[1]):
                raise LinkFailed(UNREADABLE)
            return int(band[row, col])
    except RasterioError as exc:
        raise LinkFailed(UNREADABLE) from exc


def layers_from(values: dict[tuple[str, str], int]) -> list[SoilLayer]:
    """Layers top to bottom in conventional units; raises LinkFailed without data.

    Zero in sand, silt and clay of a depth means the maps have no data there
    (masked: city, water); such a layer keeps no values.
    """
    layers = []
    for depth, (top, bottom) in params.TEXTURE_DEPTHS.items():
        fields = {
            field: values[(name, depth)] / divisor
            for field, (name, divisor) in params.TEXTURE_PROPERTIES.items()
        }
        if all(fields[field] == 0 for field in _TEXTURE_FIELDS):
            fields = dict.fromkeys(fields)
        layers.append(
            SoilLayer(
                top_cm=top,
                bottom_cm=bottom,
                **fields,
                # Not fetched: water contents of this source are not used.
                water_33kpa_vol_pct=None,
                water_1500kpa_vol_pct=None,
            )
        )
    if all(layer.sand_pct is None for layer in layers):
        raise LinkFailed(NO_DATA)
    return layers


class TextureMaps:
    """Reads texture and organic carbon of the standard depths at a point."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def read(self, lon: float, lat: float) -> list[SoilLayer]:
        """Layers down to the profile depth; raises LinkFailed."""
        x, y = map_coordinates(lon, lat)
        gate = asyncio.Semaphore(params.TEXTURE_CONCURRENCY)
        keys = [
            (name, depth)
            for name, _ in params.TEXTURE_PROPERTIES.values()
            for depth in params.TEXTURE_DEPTHS
        ]

        async def one(client: httpx.AsyncClient, name: str, depth: str) -> int:
            async with gate:
                response = await client.get(
                    params.TEXTURE_URL, params=coverage_query(name, depth, x, y)
                )
            response.raise_for_status()
            return cell_value(response.content, x, y)

        try:
            async with asyncio.timeout(params.TEXTURE_TIMEOUT_S):
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=params.TEXTURE_TIMEOUT_S,
                    headers={"User-Agent": params.USER_AGENT},
                ) as client:
                    read = await asyncio.gather(*(one(client, *key) for key in keys))
        except (httpx.HTTPError, TimeoutError) as exc:
            raise LinkFailed(UNAVAILABLE) from exc
        return layers_from(dict(zip(keys, read)))
