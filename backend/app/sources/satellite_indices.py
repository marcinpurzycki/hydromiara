"""Reading one Sentinel-2 scene over a parcel and computing its indices.

The scene classification is read first and gives the share of clear pixels
over the parcel. Bands are read only for scenes that pass. The bands come on
two grids (10 m and 20 m); indices are computed per pixel on the grid of the
red band, with the 20 m layers sampled at the centres of its pixels.

Everything here is blocking; the adapter calls it from worker threads.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any

import numpy as np
import rasterio
from rasterio.errors import RasterioError
from rasterio.io import DatasetReader

from app.sources import satellite_params as params
from app.sources.raster import EmptyReason, RasterWindow, read_window

# Opens the raster behind a file address; replaced by local files in tests.
RasterOpener = Callable[[str], AbstractContextManager[DatasetReader]]


class SceneReadError(Exception):
    """A scene file could not be read or does not fit the other files."""


@dataclass(frozen=True)
class ClearCheck:
    """Scene classification over the parcel and what it says about the scene."""

    window: RasterWindow
    clear_share_pct: float | None  # None when the window is empty
    empty_reason: EmptyReason | None

    @property
    def passes(self) -> bool:
        return (
            self.clear_share_pct is not None
            and self.clear_share_pct >= params.MIN_CLEAR_SHARE_PCT
        )


@dataclass(frozen=True)
class SceneIndices:
    """Mean indices over the clear pixels of the parcel; None without such pixels."""

    ndvi: float | None
    ndmi: float | None
    pixel_count: int


@contextmanager
def open_remote(href: str) -> Iterator[DatasetReader]:
    """Open a remote cloud-optimised file with bounded waiting."""
    with rasterio.Env(**params.GDAL_OPTIONS), rasterio.open(href) as dataset:
        yield dataset


def read_layer(
    opener: RasterOpener, href: str, geometry: Any, *, margin_m: float = 0.0
) -> RasterWindow:
    """One file of a scene read around the parcel, on the grid of that file."""
    try:
        with opener(href) as dataset:
            return read_window(
                dataset, geometry, inward_buffer_m=params.INWARD_BUFFER_M, margin_m=margin_m
            )
    except (RasterioError, OSError) as exc:
        raise SceneReadError(type(exc).__name__) from exc


def is_clear(classes: np.ma.MaskedArray) -> np.ndarray:
    """True where the scene classification holds a class counted as clear."""
    known = ~np.ma.getmaskarray(classes)
    return known & np.isin(np.ma.getdata(classes), params.CLEAR_SCL_CLASSES)


def check_clear(opener: RasterOpener, scl_href: str, geometry: Any) -> ClearCheck:
    """Read the scene classification and count clear pixels over the parcel.

    The share is counted on the classification grid: clear pixels among all
    pixels inside the outline, pixels without data counting as not clear.
    """
    window = read_layer(opener, scl_href, geometry, margin_m=params.COARSE_MARGIN_M)
    reason = window.empty_reason
    if reason is not None:
        return ClearCheck(window=window, clear_share_pct=None, empty_reason=reason)
    clear_count = int((window.inside & is_clear(window.data)).sum())
    share = round(100.0 * clear_count / window.inside_count, 1)
    return ClearCheck(window=window, clear_share_pct=share, empty_reason=None)


def to_grid(source: RasterWindow, target: RasterWindow) -> np.ma.MaskedArray:
    """Values of `source` at the pixel centres of `target` (nearest pixel).

    Target pixels whose centre lies outside the source window are masked.
    Both windows must be in the same coordinate system.
    """
    if source.crs != target.crs:
        raise SceneReadError("layers of one scene are in different coordinate systems")
    rows, cols = target.inside.shape
    t_a, _, t_c, _, t_e, t_f = target.transform
    s_a, _, s_c, _, s_e, s_f = source.transform
    xs = t_c + (np.arange(cols) + 0.5) * t_a
    ys = t_f + (np.arange(rows) + 0.5) * t_e
    src_cols = np.floor((xs - s_c) / s_a).astype(int)
    src_rows = np.floor((ys - s_f) / s_e).astype(int)
    src_height, src_width = source.data.shape
    col_ok = (src_cols >= 0) & (src_cols < src_width)
    row_ok = (src_rows >= 0) & (src_rows < src_height)
    outside = ~(row_ok[:, np.newaxis] & col_ok[np.newaxis, :])
    if src_height == 0 or src_width == 0:
        return np.ma.masked_all((rows, cols), dtype=source.data.dtype)
    picked = source.data[
        np.ix_(np.clip(src_rows, 0, src_height - 1), np.clip(src_cols, 0, src_width - 1))
    ]
    return np.ma.masked_array(
        np.ma.getdata(picked), mask=np.ma.getmaskarray(picked) | outside
    )


def _reflectance(values: np.ndarray) -> np.ndarray:
    return values.astype("float64") * params.REFLECTANCE_SCALE + params.REFLECTANCE_OFFSET


def _normalised_difference(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    return (first - second) / (first + second)


def compute_indices(
    scl: RasterWindow, red: RasterWindow, nir: RasterWindow, swir: RasterWindow
) -> SceneIndices:
    """NDVI and NDMI per pixel on the red band grid, averaged over the parcel.

    NDVI = (NIR - red) / (NIR + red)       (Rouse et al., 1974)
    NDMI = (NIR - SWIR) / (NIR + SWIR)     (Gao, 1996)

    A pixel counts when its centre lies inside the outline, all three bands
    hold data there and the scene classification marks it as clear. Both
    indices are averaged over the same pixels.
    """
    layers = [red.data, to_grid(nir, red), to_grid(swir, red)]
    classes = to_grid(scl, red)
    usable = red.inside & is_clear(classes)
    for layer in layers:
        usable &= ~np.ma.getmaskarray(layer)
    red_r, nir_r, swir_r = (_reflectance(np.ma.getdata(layer)[usable]) for layer in layers)
    usable_values = (nir_r + red_r != 0) & (nir_r + swir_r != 0)
    red_r, nir_r, swir_r = red_r[usable_values], nir_r[usable_values], swir_r[usable_values]
    if red_r.size == 0:
        return SceneIndices(ndvi=None, ndmi=None, pixel_count=0)
    ndvi = _normalised_difference(nir_r, red_r)
    ndmi = _normalised_difference(nir_r, swir_r)
    return SceneIndices(
        ndvi=round(float(ndvi.mean()), params.INDEX_DECIMALS),
        ndmi=round(float(ndmi.mean()), params.INDEX_DECIMALS),
        pixel_count=int(red_r.size),
    )
