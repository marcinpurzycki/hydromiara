"""Copernicus DEM GLO-30 as a link of the terrain chain.

Two steps: the catalogue is asked which one-degree tile covers the parcel,
then the window around the parcel is read straight from that tile, a Cloud
Optimized GeoTIFF in a public bucket. Only coordinates are sent out.

The product is a surface model: elevations include buildings and vegetation.
A parcel lying across a tile edge gets the part of the grid that the tile of
its centre holds, and the reading says so.
"""

import asyncio
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import httpx
import numpy as np
import rasterio
from rasterio.errors import RasterioError
from rasterio.io import DatasetReader
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from app.contracts.source_data import TerrainData
from app.sources import terrain_params as params
from app.sources.raster import WGS84, buffer_metres, read_window, reproject_geometry
from app.sources.terrain import TerrainLinkError, TerrainReading

DatasetOpener = Callable[[str], AbstractContextManager[DatasetReader]]

_NO_ANSWER = "katalog modelu wysokości nie odpowiedział"
_NOT_COVERED = "model wysokości nie obejmuje tego miejsca"
_UNREADABLE = "nie udało się odczytać pliku modelu wysokości"
_NO_VALUES = "model wysokości nie ma wartości dla tego miejsca"
_PARTIAL = (
    "Siatka wysokości terenu nie obejmuje całej działki z otoczeniem, "
    "bo działka leży na granicy arkuszy modelu wysokości."
)


@contextmanager
def open_public_tile(href: str) -> Iterator[DatasetReader]:
    """Open a tile of the public bucket without credentials (blocking)."""
    with rasterio.Env(
        AWS_NO_SIGN_REQUEST=True,
        AWS_REGION=params.COPERNICUS_BUCKET_REGION,
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT=int(params.COPERNICUS_READ_TIMEOUT_S),
        GDAL_HTTP_USERAGENT=params.USER_AGENT,
    ):
        with rasterio.open(href) as dataset:
            yield dataset


def tile_from_search(payload: object) -> str:
    """Address of the tile file from a catalogue answer."""
    try:
        features = payload["features"]
        if not features:
            raise TerrainLinkError(_NOT_COVERED)
        href = features[0]["assets"][params.COPERNICUS_ASSET]["href"]
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise TerrainLinkError(_NO_ANSWER) from exc
    if not isinstance(href, str) or not href.startswith(params.COPERNICUS_BUCKET_PREFIX):
        raise TerrainLinkError(_NO_ANSWER)
    return href


def elevation_rows(data: np.ma.MaskedArray) -> list[list[float | None]]:
    """Grid values in metres, rounded to centimetres; None where there is no data."""
    values = np.ma.getdata(data).astype("float64").round(2)
    missing = np.ma.getmaskarray(data) | ~np.isfinite(values)
    return [
        [None if absent else float(value) for value, absent in zip(row, absent_row, strict=True)]
        for row, absent_row in zip(values, missing, strict=True)
    ]


def read_grid(
    open_dataset: DatasetOpener, href: str, outline: BaseGeometry
) -> tuple[TerrainData, bool]:
    """Grid around the outline from one tile, and whether the tile holds all of it.

    Blocking: opens the tile and reads the window.
    """
    try:
        with open_dataset(href) as dataset:
            window = read_window(
                dataset, outline, inward_buffer_m=0.0, margin_m=params.WINDOW_MARGIN_M
            )
            wanted = reproject_geometry(
                buffer_metres(outline, WGS84, params.WINDOW_MARGIN_M),
                WGS84,
                dataset.crs.to_wkt(),
            )
            complete = box(*dataset.bounds).covers(box(*wanted.bounds))
    except (RasterioError, OSError) as exc:
        raise TerrainLinkError(_UNREADABLE) from exc

    if window.data.size == 0:
        raise TerrainLinkError(_NOT_COVERED)
    rows = elevation_rows(window.data)
    if all(value is None for row in rows for value in row):
        raise TerrainLinkError(_NO_VALUES)
    data = TerrainData(
        resolution_m=params.COPERNICUS_RESOLUTION_M,
        crs=window.crs,
        transform=window.transform,
        elevations_m=rows,
    )
    return data, complete


class CopernicusDem30:
    """Elevation grid of about 30 m from the Copernicus DEM."""

    name = params.COPERNICUS_SOURCE_NAME
    timeout_s = params.COPERNICUS_LINK_TIMEOUT_S

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        open_dataset: DatasetOpener = open_public_tile,
    ) -> None:
        self._transport = transport
        self._open_dataset = open_dataset

    async def find_tile(self, lon: float, lat: float) -> str:
        """Ask the catalogue for the address of the tile covering the point."""
        body = {
            "collections": [params.COPERNICUS_COLLECTION],
            "intersects": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "limit": 1,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=params.COPERNICUS_SEARCH_TIMEOUT_S,
                headers={"User-Agent": params.USER_AGENT},
            ) as client:
                response = await client.post(params.COPERNICUS_SEARCH_URL, json=body)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TerrainLinkError(_NO_ANSWER) from exc
        return tile_from_search(payload)

    async def read(self, outline: BaseGeometry) -> TerrainReading:
        """Grid around the outline (EPSG:4326) from the tile of its centre."""
        centre = outline.centroid
        href = await self.find_tile(centre.x, centre.y)
        data, complete = await asyncio.to_thread(read_grid, self._open_dataset, href, outline)
        return TerrainReading(
            data=data,
            data_date=params.COPERNICUS_DATA_DATE,
            note=None if complete else _PARTIAL,
        )
