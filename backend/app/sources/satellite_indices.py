"""Reading one Sentinel-2 scene over a parcel and computing its indices.

The scene classification is read first and gives the share of clear pixels
over the parcel. Bands are read only for scenes that pass. Each index is
computed on the grid of its own bands, from clear pixels only, and the value
of the scene is the median over those pixels:

    NDVI = (B08 - B04) / (B08 + B04)   on the 10 m grid   (Rouse et al., 1974)
    NDMI = (B8A - B11) / (B8A + B11)   on the 20 m grid   (Gao, 1996)

The parcel outline is shrunk by half a pixel of the grid before pixels are
counted. An index needs a minimum number of pixels, so a narrow parcel may
give NDVI alone, or nothing.

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
from rasterio.transform import Affine

from app.sources import satellite_params as params
from app.sources.raster import EmptyReason, RasterWindow, outline_mask
from app.sources.satellite_outline import as_outline, read_outline_window

# Opens the raster behind a file address; replaced by local files in tests.
RasterOpener = Callable[[str], AbstractContextManager[DatasetReader]]


class SceneReadError(Exception):
    """A scene file could not be read, does not fit the other files or holds no usable values."""


@dataclass(frozen=True)
class ClearCheck:
    """Scene classification over the parcel and what it says about the scene."""

    window: RasterWindow  # classification, outline shrunk as for the 20 m grid
    clear_share_pct: float | None  # None when nothing can be counted
    empty_reason: EmptyReason | None
    coarse_pixels: int  # 20 m pixels inside the outline shrunk by the 20 m buffer
    # 10 m pixels inside the outline shrunk by the 10 m buffer; counted only
    # for a parcel with too few 20 m pixels, None otherwise.
    fine_pixels: int | None

    @property
    def passes(self) -> bool:
        return (
            self.clear_share_pct is not None
            and self.clear_share_pct >= params.MIN_CLEAR_SHARE_PCT
        )

    @property
    def ndvi_possible(self) -> bool:
        return self.fine_pixels is None or self.fine_pixels >= params.MIN_PIXELS

    @property
    def ndmi_possible(self) -> bool:
        return self.coarse_pixels >= params.MIN_PIXELS


@dataclass(frozen=True)
class SceneIndices:
    """Median indices over the clear pixels of the parcel; None below the pixel minimum."""

    ndvi: float | None
    ndmi: float | None
    ndvi_pixels: int
    ndmi_pixels: int


@contextmanager
def open_remote(href: str) -> Iterator[DatasetReader]:
    """Open a remote cloud-optimised file with bounded waiting."""
    with rasterio.Env(**params.GDAL_OPTIONS), rasterio.open(href) as dataset:
        yield dataset


def read_layer(
    opener: RasterOpener, href: str, geometry: Any, *, buffer_m: float, margin_m: float = 0.0
) -> RasterWindow:
    """One file of a scene read around the parcel, on the grid of that file.

    `geometry` is the outline as GeoJSON or, to reuse its conversions between
    reads, a prepared `ParcelOutline`.
    """
    try:
        with opener(href) as dataset:
            return read_outline_window(
                dataset, as_outline(geometry), buffer_m=buffer_m, margin_m=margin_m
            )
    except (RasterioError, OSError) as exc:
        raise SceneReadError(type(exc).__name__) from exc


def is_clear(classes: np.ma.MaskedArray) -> np.ndarray:
    """True where the scene classification holds a class counted as clear."""
    known = ~np.ma.getmaskarray(classes)
    return known & np.isin(np.ma.getdata(classes), params.CLEAR_SCL_CLASSES)


def _to_fine(grid: np.ndarray) -> np.ndarray:
    """A 20 m grid repeated onto the 10 m grid: every pixel becomes 2 x 2 pixels."""
    return np.repeat(np.repeat(grid, 2, axis=0), 2, axis=1)


def _fine_inside(window: RasterWindow, geometry: Any) -> np.ndarray:
    """Pixels of the 10 m grid under the classification window that lie inside the parcel.

    The two grids share their corners, so the 10 m grid is the classification
    grid halved. The outline is shrunk by the buffer of the 10 m grid.
    """
    a, b, c, d, e, f = window.transform
    core = as_outline(geometry).in_crs(window.crs, -params.FINE_BUFFER_M)
    rows, cols = window.data.shape
    return outline_mask(core, (2 * rows, 2 * cols), Affine(a / 2, b, c, d, e / 2, f))


def check_clear(opener: RasterOpener, scl_href: str, geometry: Any) -> ClearCheck:
    """Read the scene classification and count clear pixels over the parcel.

    The share is counted on the classification grid, among the pixels inside
    the outline; pixels without data count as not clear. A parcel with too few
    such pixels for NDMI but enough 10 m pixels for NDVI is counted on the
    10 m grid instead, each classification pixel standing for its four pixels.
    """
    window = read_layer(
        opener,
        scl_href,
        geometry,
        buffer_m=params.COARSE_BUFFER_M,
        margin_m=params.COARSE_MARGIN_M,
    )

    def result(
        share: float | None, reason: EmptyReason | None, fine: int | None = None
    ) -> ClearCheck:
        return ClearCheck(window, share, reason, window.inside_count, fine)

    if window.data.size == 0:
        return result(None, "outside_raster")
    inside, fine_pixels = window.inside, None
    known = ~np.ma.getmaskarray(window.data)
    clear = is_clear(window.data)
    if window.inside_count < params.MIN_PIXELS:
        inside, known, clear = _fine_inside(window, geometry), _to_fine(known), _to_fine(clear)
        fine_pixels = int(inside.sum())
        if fine_pixels < params.MIN_PIXELS:
            return result(None, "parcel_too_small", fine_pixels)
    if not (inside & known).any():
        return result(None, "no_valid_data", fine_pixels)
    share = round(100.0 * int((inside & clear).sum()) / int(inside.sum()), 1)
    return result(share, None, fine_pixels)


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


def _index(
    scl: RasterWindow, near: RasterWindow, other: RasterWindow, offset: float
) -> tuple[float | None, int]:
    """Median of (near - other) / (near + other) over the clear pixels, and their number.

    A pixel counts when its centre lies inside the shrunk outline, both bands
    hold data there and the classification marks it as clear. Below the pixel
    minimum there is no value. Raises when the median reflectance of a band
    over those pixels is not positive: the stored values are then not what
    the offset rule assumes, and the scene is not used.
    """
    second = to_grid(other, near)
    usable = near.inside & is_clear(to_grid(scl, near))
    usable &= ~np.ma.getmaskarray(near.data) & ~np.ma.getmaskarray(second)
    count = int(usable.sum())
    if count < params.MIN_PIXELS:
        return None, count
    near_r, other_r = (
        np.ma.getdata(layer)[usable].astype("float64") * params.REFLECTANCE_SCALE + offset
        for layer in (near.data, second)
    )
    if np.median(near_r) <= 0 or np.median(other_r) <= 0:
        raise SceneReadError("median reflectance over the parcel is not positive")
    total = near_r + other_r
    values = (near_r - other_r)[total != 0] / total[total != 0]
    if values.size < params.MIN_PIXELS:
        return None, int(values.size)
    return round(float(np.median(values)), params.INDEX_DECIMALS), count


def compute_indices(
    scl: RasterWindow,
    red: RasterWindow | None,
    nir: RasterWindow | None,
    nir_narrow: RasterWindow | None,
    swir: RasterWindow | None,
    reflectance_offset: float = 0.0,
) -> SceneIndices:
    """NDVI from the 10 m bands and NDMI from the 20 m bands of one scene.

    A pair of bands that was not read (None) gives no index.
    """
    ndvi, ndvi_pixels = (None, 0)
    ndmi, ndmi_pixels = (None, 0)
    if red is not None and nir is not None:
        ndvi, ndvi_pixels = _index(scl, nir, red, reflectance_offset)
    if nir_narrow is not None and swir is not None:
        ndmi, ndmi_pixels = _index(scl, nir_narrow, swir, reflectance_offset)
    return SceneIndices(ndvi=ndvi, ndmi=ndmi, ndvi_pixels=ndvi_pixels, ndmi_pixels=ndmi_pixels)
