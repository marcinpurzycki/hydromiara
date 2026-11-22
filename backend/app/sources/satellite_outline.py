"""The parcel outline prepared once per adapter call for every grid it is read on.

One call reads well over a hundred scene files, all on a handful of grids.
Converting and shrinking the outline is the costly part of a read, so each
variant (coordinate system, distance) is computed once and reused; the read
itself is put together from the steps of raster.py.
"""

import threading
from typing import Any

import numpy as np
from rasterio.io import DatasetReader
from shapely.geometry.base import BaseGeometry

from app.sources.raster import (
    WGS84,
    RasterWindow,
    as_geometry,
    buffer_metres,
    geometry_window,
    outline_mask,
    reproject_geometry,
)


class ParcelOutline:
    """A parcel outline (longitude, latitude) with its converted variants kept."""

    def __init__(self, geometry: Any) -> None:
        self._outline = as_geometry(geometry)
        if self._outline.is_empty or self._outline.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("parcel outline must be a non-empty Polygon or MultiPolygon")
        self._variants: dict[tuple[str, float], BaseGeometry] = {}
        self._lock = threading.Lock()

    def in_crs(self, crs: str, grow_m: float = 0.0) -> BaseGeometry:
        """The outline in `crs`, grown (positive) or shrunk (negative) by metres."""
        key = (crs, grow_m)
        with self._lock:
            if key not in self._variants:
                changed = buffer_metres(self._outline, WGS84, grow_m)
                self._variants[key] = reproject_geometry(changed, WGS84, crs)
            return self._variants[key]


def as_outline(geometry: Any) -> ParcelOutline:
    return geometry if isinstance(geometry, ParcelOutline) else ParcelOutline(geometry)


def read_outline_window(
    dataset: DatasetReader, outline: ParcelOutline, *, buffer_m: float, margin_m: float = 0.0
) -> RasterWindow:
    """Read band 1 around the outline; the same result as `raster.read_window`.

    The window covers the outline grown by `margin_m`; `inside` marks pixels
    whose centre lies within the outline shrunk by `buffer_m`.
    """
    crs = dataset.crs.to_string()
    resolution = (float(dataset.res[0]), float(dataset.res[1]))
    window = geometry_window(dataset, outline.in_crs(crs, margin_m))
    if window is None:
        t = dataset.transform
        return RasterWindow(
            data=np.ma.masked_all((0, 0), dtype=dataset.dtypes[0]),
            inside=np.zeros((0, 0), dtype=bool),
            transform=(t.a, t.b, t.c, t.d, t.e, t.f),
            crs=crs,
            resolution=resolution,
        )
    data = dataset.read(1, window=window, masked=True)
    t = dataset.window_transform(window)
    inside = outline_mask(outline.in_crs(crs, -buffer_m), data.shape, t)
    return RasterWindow(
        data=data,
        inside=inside,
        transform=(t.a, t.b, t.c, t.d, t.e, t.f),
        crs=crs,
        resolution=resolution,
    )
