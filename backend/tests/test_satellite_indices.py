"""Clear-pixel share, the common grid and the indices on rasters built in the test."""

import numpy as np
import pytest

from app.sources import satellite_params as params
from app.sources.raster import RasterWindow
from app.sources.satellite_indices import (
    SceneReadError,
    check_clear,
    compute_indices,
    is_clear,
    read_layer,
    to_grid,
)
from tests.satellite_helpers import OUTLINE, SceneFiles, hrefs_of, scene_id

UTM = "EPSG:32634"
WEST, NORTH = 500_000.0, 5_800_000.0
GEOMETRY = OUTLINE.model_dump()


def window(values, pixel_m, *, west=WEST, north=NORTH, inside=None, masked=None, crs=UTM):
    """A raster window built by hand: upper-left corner, pixel size and values."""
    data = np.ma.masked_array(np.asarray(values), mask=masked if masked is not None else False)
    return RasterWindow(
        data=data,
        inside=np.ones(data.shape, dtype=bool) if inside is None else np.asarray(inside),
        transform=(pixel_m, 0.0, west, 0.0, -pixel_m, north),
        crs=crs,
        resolution=(pixel_m, pixel_m),
    )


def fine(values, **kwargs):
    return window(np.asarray(values, dtype="uint16"), 10.0, **kwargs)


def coarse(values, **kwargs):
    return window(np.asarray(values, dtype="uint16"), 20.0, **kwargs)


def test_each_coarse_pixel_covers_four_fine_pixels():
    on_fine = to_grid(coarse([[1, 2], [3, 4]]), fine(np.zeros((4, 4))))
    assert on_fine.tolist() == [[1, 1, 2, 2], [1, 1, 2, 2], [3, 3, 4, 4], [3, 3, 4, 4]]


def test_coarse_window_with_another_corner_is_placed_by_coordinates():
    # The coarse window starts 20 m west and north of the fine one.
    source = coarse([[1, 2, 3], [4, 5, 6], [7, 8, 9]], west=WEST - 20, north=NORTH + 20)
    on_fine = to_grid(source, fine(np.zeros((2, 4))))
    assert on_fine.tolist() == [[5, 5, 6, 6], [5, 5, 6, 6]]


def test_unaligned_grids_take_the_pixel_under_each_centre():
    # Shifted by 10 m: fine columns 0 and 3 fall into different coarse pixels than 1-2.
    source = coarse([[1, 2, 3]], west=WEST - 10)
    assert to_grid(source, fine(np.zeros((1, 4)))).tolist() == [[1, 2, 2, 3]]


def test_fine_pixels_outside_the_coarse_window_are_masked():
    on_fine = to_grid(coarse([[7]]), fine(np.zeros((2, 4))))
    assert on_fine.tolist() == [[7, 7, None, None], [7, 7, None, None]]


def test_missing_coarse_values_stay_missing_on_the_fine_grid():
    source = coarse([[1, 2]], masked=[[False, True]])
    assert to_grid(source, fine(np.zeros((2, 4)))).tolist() == [[1, 1, None, None]] * 2


def test_layers_in_different_coordinate_systems_are_refused():
    with pytest.raises(SceneReadError):
        to_grid(coarse([[1]], crs="EPSG:32633"), fine(np.zeros((2, 2))))


def test_only_listed_classes_are_clear():
    classes = np.ma.masked_array(
        np.array([[4, 5, 9, 3, 4]], dtype="uint8"), mask=[[False, False, False, False, True]]
    )
    assert is_clear(classes).tolist() == [[True, True, False, False, False]]
    assert params.CLEAR_SCL_CLASSES == (4, 5)


def test_indices_on_known_values():
    grid = np.ones((4, 4))
    scl, swir = coarse(np.full((2, 2), 4)), coarse(np.full((2, 2), 2000))
    result = compute_indices(scl, fine(1000 * grid), fine(3000 * grid), swir)
    assert result.ndvi == pytest.approx(0.5)  # (3000 - 1000) / (3000 + 1000)
    assert result.ndmi == pytest.approx(0.2)  # (3000 - 2000) / (3000 + 2000)
    assert result.pixel_count == 16


def test_indices_are_averaged_per_pixel_not_computed_from_band_means():
    # West half: NDVI 0.5, NDMI 0.2. East half: NDVI 0.0, NDMI -0.5.
    red = fine([[1000, 1000, 1000, 1000]] * 2)
    nir = fine([[3000, 3000, 1000, 1000]] * 2)
    swir = coarse([[2000, 3000]])
    result = compute_indices(coarse([[4, 5]]), red, nir, swir)
    assert result.ndvi == pytest.approx(0.25)
    assert result.ndmi == pytest.approx(-0.15)
    band_means_ndvi = (2000 - 1000) / (2000 + 1000)
    assert result.ndvi != pytest.approx(band_means_ndvi)


def test_cloudy_missing_and_outside_pixels_do_not_count():
    red = fine([[1000, 1000, 1000, 1000, 1000, 1000]] * 2)
    nir = fine(
        [[3000, 3000, 9000, 9000, 9000, 9000]] * 2,
        masked=[[False, False, False, False, True, True]] * 2,
    )
    inside = [[True, False, True, True, True, True]] * 2
    red = fine(np.ma.getdata(red.data), inside=inside)
    scl = coarse([[4, 9, 4]])  # the middle coarse pixel is cloud
    result = compute_indices(scl, red, nir, coarse([[2000, 2000, 2000]]))
    # Left: column 0 only (column 1 outside); middle: cloud; right: no NIR data.
    assert result.pixel_count == 2
    assert result.ndvi == pytest.approx(0.5)


def test_no_usable_pixel_gives_no_indices():
    grid = np.ones((2, 2))
    result = compute_indices(coarse([[9]]), fine(1000 * grid), fine(3000 * grid), coarse([[2000]]))
    assert (result.ndvi, result.ndmi, result.pixel_count) == (None, None, 0)


def test_reflectance_offset_enters_the_indices():
    grid = np.ones((2, 2))
    result = compute_indices(
        coarse([[4]]), fine(2000 * grid), fine(4000 * grid), coarse([[3000]]), -0.1
    )
    assert result.ndvi == pytest.approx((0.3 - 0.1) / (0.3 + 0.1))


def test_clear_share_is_counted_over_the_parcel(tmp_path):
    files = SceneFiles(tmp_path)
    scene = scene_id("20230619")
    classes = np.full((30, 30), 4, dtype="uint8")
    classes[:, 15:] = 9  # the east half of the raster is cloud
    files.add(scene, scl=classes)
    check = check_clear(files.opener, hrefs_of(scene)["scl"], GEOMETRY)
    assert check.empty_reason is None
    assert 0 < check.clear_share_pct < 100
    inside = check.window.inside
    expected = 100 * (inside & (np.ma.getdata(check.window.data) == 4)).sum() / inside.sum()
    assert check.clear_share_pct == pytest.approx(expected, abs=0.05)
    assert check.passes == (check.clear_share_pct >= params.MIN_CLEAR_SHARE_PCT)


def test_threshold_decides_whether_a_scene_passes(tmp_path, monkeypatch):
    files = SceneFiles(tmp_path)
    scene = scene_id("20230619")
    files.add(scene, scl=4)
    check = check_clear(files.opener, hrefs_of(scene)["scl"], GEOMETRY)
    assert check.clear_share_pct == 100.0 and check.passes
    monkeypatch.setattr(params, "MIN_CLEAR_SHARE_PCT", 100.1)
    assert not check.passes


def test_file_that_cannot_be_opened_is_a_scene_read_error(tmp_path):
    broken = tmp_path / "broken.tif"
    broken.write_bytes(b"not a raster")
    files = SceneFiles(tmp_path)
    files._paths["https://example.invalid/broken.tif"] = broken
    with pytest.raises(SceneReadError):
        read_layer(files.opener, "https://example.invalid/broken.tif", GEOMETRY)
