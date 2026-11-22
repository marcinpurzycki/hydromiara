"""Shared raster reading for source adapters.

Reads the part of a raster that covers a parcel and tells which pixels lie
inside the parcel outline. Three steps, each usable on its own:

1. coordinate conversion of the outline (`reproject_geometry`, `buffer_metres`),
2. the pixel window around the outline (`geometry_window`),
3. the outline mask on the window grid (`outline_mask`).

`read_window` combines them. Finding the files, opening them and interpreting
the values belong to the adapters. Reading is blocking I/O: call it from a
worker thread when the dataset is remote.

Only north-up rasters (no rotation) are supported.
"""

import math
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from pyproj import Transformer
from rasterio import features
from rasterio.io import DatasetReader
from rasterio.windows import Window
from shapely import transform as transform_coordinates
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.contracts.common import GeoJsonGeometry

# Parcel outlines arrive as GeoJSON: longitude, latitude.
WGS84 = "EPSG:4326"

# PL-1992, the national projected system for the whole of Poland, in metres.
# Distances given in metres (buffers, margins) are applied in this system.
METRIC_CRS = "EPSG:2180"

# PROVISIONAL: no source yet for how far pixels must lie from the parcel
# boundary to be free of neighbouring land cover; one 10 m pixel is assumed.
DEFAULT_INWARD_BUFFER_M = 10.0

# Bounds this close to a pixel edge count as lying on it, so that floating
# point noise does not add a row or column to the window.
_EDGE_TOLERANCE_PX = 1e-6

# One rasterize call at a time. Adapters read rasters in parallel threads, and
# concurrent calls now and then raised NotGeoreferencedWarning although every
# mask was correct. The lock rules out parallel rasterize calls; it rests on
# our own measurement (outline_mask alone from many threads: no warning with
# the lock), not on the rasterio documentation, which does not describe
# rasterize under threads. The warning still shows up now and then in the
# full test run and its origin is not established.
_RASTERIZE_LOCK = threading.Lock()

EmptyReason = Literal["outside_raster", "parcel_too_small", "no_valid_data"]

AffineTuple = tuple[float, float, float, float, float, float]

OutlineInput = BaseGeometry | GeoJsonGeometry | Mapping[str, Any]


@dataclass(frozen=True)
class RasterWindow:
    """One band read around a parcel, with the outline mask on the same grid.

    `data` is a 2-D masked array, rows from north to south; pixels without
    data in the raster are masked. `inside` marks pixels whose centre lies
    within the outline after the inward buffer. Both have the same shape,
    which is (0, 0) when the parcel does not overlap the raster.
    """

    data: np.ma.MaskedArray
    inside: np.ndarray
    transform: AffineTuple  # (a, b, c, d, e, f): window pixel -> CRS coordinates
    crs: str
    resolution: tuple[float, float]  # pixel width and height in CRS units

    @property
    def inside_count(self) -> int:
        """Pixels within the outline, with or without data."""
        return int(self.inside.sum())

    @property
    def valid(self) -> np.ndarray:
        """Pixels within the outline that hold data."""
        return self.inside & ~np.ma.getmaskarray(self.data)

    def values(self) -> np.ndarray:
        """Data values of the valid pixels as a flat array."""
        return np.ma.getdata(self.data)[self.valid]

    @property
    def empty_reason(self) -> EmptyReason | None:
        """Why there is nothing to compute from, or None when there is."""
        if self.data.size == 0:
            return "outside_raster"
        if self.inside_count == 0:
            return "parcel_too_small"
        if not self.valid.any():
            return "no_valid_data"
        return None


def as_geometry(geometry: OutlineInput) -> BaseGeometry:
    """Accept a shapely geometry, a contract geometry or a GeoJSON-like mapping."""
    if isinstance(geometry, BaseGeometry):
        return geometry
    if isinstance(geometry, GeoJsonGeometry):
        return shape(geometry.model_dump())
    return shape(geometry)


def reproject_geometry(geometry: BaseGeometry, src_crs: Any, dst_crs: Any) -> BaseGeometry:
    """Convert geometry coordinates between systems, always in x, y order.

    Both systems may be anything pyproj accepts (EPSG string or code, WKT).
    Only vertices are converted, which is accurate for parcel-sized shapes.
    """
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return transform_coordinates(geometry, transformer.transform, interleaved=False)


def buffer_metres(geometry: BaseGeometry, crs: Any, distance_m: float) -> BaseGeometry:
    """Grow (positive) or shrink (negative) a geometry by a distance in metres.

    The result stays in `crs`. Shrinking a shape narrower than twice the
    distance gives an empty geometry.
    """
    if distance_m == 0:
        return geometry
    metric = reproject_geometry(geometry, crs, METRIC_CRS).buffer(distance_m)
    return reproject_geometry(metric, METRIC_CRS, crs)


def geometry_window(dataset: DatasetReader, geometry: BaseGeometry) -> Window | None:
    """Smallest whole-pixel window of the dataset covering the geometry bounds.

    The geometry must be in the dataset CRS. The window is clipped to the
    dataset; None means the geometry is empty or lies outside the raster.
    """
    if geometry.is_empty:
        return None
    window = dataset.window(*geometry.bounds)
    col_start = max(math.floor(window.col_off + _EDGE_TOLERANCE_PX), 0)
    row_start = max(math.floor(window.row_off + _EDGE_TOLERANCE_PX), 0)
    col_stop = min(math.ceil(window.col_off + window.width - _EDGE_TOLERANCE_PX), dataset.width)
    row_stop = min(math.ceil(window.row_off + window.height - _EDGE_TOLERANCE_PX), dataset.height)
    if col_stop <= col_start or row_stop <= row_start:
        return None
    return Window(col_start, row_start, col_stop - col_start, row_stop - row_start)


def outline_mask(geometry: BaseGeometry, out_shape: tuple[int, int], transform: Any) -> np.ndarray:
    """Boolean grid: True where the pixel centre lies within the geometry.

    The geometry must be in the CRS of `transform` (an affine transform of
    the target grid). An empty geometry gives an all-False grid.
    """
    if geometry.is_empty or 0 in out_shape:
        return np.zeros(out_shape, dtype=bool)
    with _RASTERIZE_LOCK:
        burned = features.rasterize(
            [(geometry, 1)],
            out_shape=out_shape,
            transform=transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        )
    return burned == 1


def read_window(
    dataset: DatasetReader,
    geometry: OutlineInput,
    *,
    geometry_crs: Any = WGS84,
    inward_buffer_m: float = DEFAULT_INWARD_BUFFER_M,
    margin_m: float = 0.0,
    band: int = 1,
) -> RasterWindow:
    """Read one band around a parcel outline.

    The window covers the outline grown by `margin_m`; `inside` marks pixels
    whose centre lies within the outline shrunk by `inward_buffer_m`. Both
    distances are in metres whatever the raster CRS.

    A parcel outside the raster, or too small to contain a pixel centre, is
    a normal result: see `RasterWindow.empty_reason`.
    """
    if inward_buffer_m < 0 or margin_m < 0:
        raise ValueError("inward_buffer_m and margin_m must not be negative")
    outline = as_geometry(geometry)
    if outline.is_empty or outline.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("parcel outline must be a non-empty Polygon or MultiPolygon")

    raster_crs = dataset.crs.to_wkt()
    crs_name = dataset.crs.to_string()
    resolution = (float(dataset.res[0]), float(dataset.res[1]))

    extent = buffer_metres(outline, geometry_crs, margin_m)
    window = geometry_window(dataset, reproject_geometry(extent, geometry_crs, raster_crs))
    if window is None:
        return RasterWindow(
            data=np.ma.masked_all((0, 0), dtype=dataset.dtypes[band - 1]),
            inside=np.zeros((0, 0), dtype=bool),
            transform=_affine_tuple(dataset.transform),
            crs=crs_name,
            resolution=resolution,
        )

    data = dataset.read(band, window=window, masked=True)
    transform = dataset.window_transform(window)
    core = buffer_metres(outline, geometry_crs, -inward_buffer_m)
    inside = outline_mask(
        reproject_geometry(core, geometry_crs, raster_crs), data.shape, transform
    )
    return RasterWindow(
        data=data,
        inside=inside,
        transform=_affine_tuple(transform),
        crs=crs_name,
        resolution=resolution,
    )


def _affine_tuple(transform: Any) -> AffineTuple:
    return (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)
