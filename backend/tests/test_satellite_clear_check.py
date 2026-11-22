"""Clear-pixel share of a scene, the two buffers and parcels too narrow for a grid."""

import numpy as np
import pytest
from shapely.geometry import Point

from app.sources import satellite_params as params
from app.sources.raster import WGS84, as_geometry, buffer_metres, reproject_geometry
from app.sources.satellite_indices import check_clear, read_layer
from tests.satellite_helpers import (
    NARROW,
    OUTLINE,
    TINY,
    SceneFiles,
    grid_origin,
    hrefs_of,
    scene_id,
)

GEOMETRY = OUTLINE.model_dump()


def centres_inside(check, buffer_m, pixel_m):
    """Pixel centres of the grid of `pixel_m` inside the outline shrunk by `buffer_m`."""
    core = buffer_metres(as_geometry(GEOMETRY), WGS84, -buffer_m)
    core = reproject_geometry(core, WGS84, check.window.crs)
    _, _, west, _, _, north = check.window.transform
    rows, cols = (int(n * 20 / pixel_m) for n in check.window.data.shape)
    return sum(
        core.contains(Point(west + (col + 0.5) * pixel_m, north - (row + 0.5) * pixel_m))
        for row in range(rows)
        for col in range(cols)
    )


def clear_check(tmp_path, scl=4, geometry=GEOMETRY):
    files = SceneFiles(tmp_path)
    name = scene_id("20230619")
    files.add(name, scl=scl)
    return check_clear(files.opener, hrefs_of(name)["scl"], geometry)


def test_outline_is_shrunk_by_5_m_on_the_fine_grid_and_10_m_on_the_coarse_grid(tmp_path):
    assert (params.FINE_BUFFER_M, params.COARSE_BUFFER_M) == (5.0, 10.0)
    files = SceneFiles(tmp_path)
    name = scene_id("20230619")
    files.add(name)
    check = check_clear(files.opener, hrefs_of(name)["scl"], GEOMETRY)
    fine_pixels = read_layer(
        files.opener, hrefs_of(name)["red"], GEOMETRY, buffer_m=params.FINE_BUFFER_M
    ).inside_count
    assert fine_pixels == centres_inside(check, 5.0, 10.0)
    assert check.coarse_pixels == centres_inside(check, 10.0, 20.0)
    assert check.coarse_pixels == check.window.inside_count
    # The two buffers really differ: one buffer for both grids gives other counts.
    assert fine_pixels > centres_inside(check, 10.0, 10.0)
    assert check.coarse_pixels < centres_inside(check, 5.0, 20.0)
    assert check.fine_pixels is None and check.ndvi_possible and check.ndmi_possible


def cloud_over(check, pixels: int) -> np.ndarray:
    """Classification raster with cloud on the first `pixels` pixels inside the parcel."""
    west, north = grid_origin(check.window.crs)
    col_off = round((check.window.transform[2] - west) / 20)
    row_off = round((north - check.window.transform[5]) / 20)
    classes = np.full((30, 30), 4, dtype="uint8")
    for row, col in np.argwhere(check.window.inside)[:pixels]:
        classes[row_off + row, col_off + col] = 9
    return classes


def test_scene_is_clear_from_95_percent_of_clear_pixels(tmp_path):
    assert params.MIN_CLEAR_SHARE_PCT == 95.0
    clear = clear_check(tmp_path)
    assert clear.clear_share_pct == 100.0 and clear.passes
    total = clear.coarse_pixels
    allowed = int(total * 0.05)  # cloud pixels that still leave 95%
    assert allowed >= 1
    at_limit = clear_check(tmp_path, scl=cloud_over(clear, allowed))
    assert at_limit.clear_share_pct == pytest.approx(100 * (total - allowed) / total, abs=0.05)
    assert at_limit.passes
    below = clear_check(tmp_path, scl=cloud_over(clear, allowed + 1))
    assert 80.0 < below.clear_share_pct < 95.0  # passed the former 80% threshold
    assert not below.passes


def test_pixels_without_data_count_as_not_clear(tmp_path):
    clear = clear_check(tmp_path)
    classes = cloud_over(clear, 5)
    classes[classes == 9] = 0  # no data
    check = clear_check(tmp_path, scl=classes)
    expected = 100 * (clear.coarse_pixels - 5) / clear.coarse_pixels
    assert check.clear_share_pct == pytest.approx(expected, abs=0.05)


def test_narrow_parcel_is_counted_on_the_fine_grid_and_gives_ndvi_only(tmp_path):
    check = clear_check(tmp_path, geometry=NARROW.model_dump())
    assert check.coarse_pixels < params.MIN_PIXELS <= check.fine_pixels
    assert check.empty_reason is None and check.clear_share_pct == 100.0
    assert check.ndvi_possible and not check.ndmi_possible
    cloudy = clear_check(tmp_path, scl=9, geometry=NARROW.model_dump())
    assert cloudy.clear_share_pct == 0.0 and not cloudy.passes


def test_parcel_with_too_few_pixels_on_both_grids_is_too_small(tmp_path):
    check = clear_check(tmp_path, geometry=TINY.model_dump())
    assert check.empty_reason == "parcel_too_small"
    assert check.fine_pixels < params.MIN_PIXELS and check.clear_share_pct is None


@pytest.mark.parametrize(("layer", "buffer_m", "margin_m"), [("scl", 10.0, 20.0), ("red", 5.0, 0.0)])
def test_prepared_outline_reads_the_same_window_as_the_shared_raster_reader(
    tmp_path, layer, buffer_m, margin_m
):
    from app.sources.raster import read_window
    from app.sources.satellite_outline import ParcelOutline

    files = SceneFiles(tmp_path)
    name = scene_id("20230619")
    files.add(name)
    href = hrefs_of(name)[layer]
    outline = ParcelOutline(GEOMETRY)
    ours = read_layer(files.opener, href, outline, buffer_m=buffer_m, margin_m=margin_m)
    again = read_layer(files.opener, href, outline, buffer_m=buffer_m, margin_m=margin_m)
    with files.opener(href) as dataset:
        shared = read_window(dataset, GEOMETRY, inward_buffer_m=buffer_m, margin_m=margin_m)
    for window in (ours, again):
        assert (window.inside == shared.inside).all() and window.inside_count > 0
        assert (window.data == shared.data).all()
        assert window.transform == shared.transform
        assert (window.crs, window.resolution) == (shared.crs, shared.resolution)
