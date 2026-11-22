"""Clear-pixel share, buffers, pixel minimum and the indices on rasters built in the test."""

import numpy as np
import pytest

from app.sources import satellite_params as params
from app.sources.raster import RasterWindow
from app.sources.satellite_indices import (
    SceneReadError,
    compute_indices,
    is_clear,
    read_layer,
    to_grid,
)
from tests.satellite_helpers import OUTLINE, SceneFiles

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


def scene(*, scl=4, red=1000, nir=3000, nir08=3000, swir=2000, fine_inside=None, coarse_inside=None):
    """Windows of one scene: a 6 x 6 block of 10 m pixels over 3 x 3 pixels of 20 m."""
    return (
        coarse(np.broadcast_to(scl, (3, 3))),
        fine(np.broadcast_to(red, (6, 6)), inside=fine_inside),
        fine(np.broadcast_to(nir, (6, 6)), inside=fine_inside),
        coarse(np.broadcast_to(nir08, (3, 3)), inside=coarse_inside),
        coarse(np.broadcast_to(swir, (3, 3)), inside=coarse_inside),
    )


def test_ndvi_comes_from_the_fine_bands_and_ndmi_from_the_coarse_bands():
    result = compute_indices(*scene(nir=3000, nir08=4000))
    assert result.ndvi == pytest.approx(0.5)  # (3000 - 1000) / (3000 + 1000), B08 and B04
    assert result.ndmi == pytest.approx(0.3333)  # (4000 - 2000) / (4000 + 2000), B8A and B11
    assert (result.ndvi_pixels, result.ndmi_pixels) == (36, 9)


def test_scene_value_is_the_median_not_the_mean():
    nir = np.full((6, 6), 3000)
    nir[0, :5] = 1000  # five pixels with NDVI 0.0 among 36 with NDVI 0.5
    swir = np.full((3, 3), 2000)
    swir[0, 0] = 3000  # one pixel with NDMI 0.0 among 9 with NDMI 0.2
    result = compute_indices(*scene(nir=nir, swir=swir))
    assert result.ndvi == pytest.approx(0.5)
    assert result.ndmi == pytest.approx(0.2)


def test_cloudy_missing_and_outside_pixels_do_not_count():
    scl = np.full((3, 3), 4)
    scl[0, 0] = 9  # cloud: four 10 m pixels and one 20 m pixel
    inside = np.ones((6, 6), dtype=bool)
    inside[5, :] = False  # six 10 m pixels outside the outline
    windows = list(scene(scl=scl, fine_inside=inside))
    nir = windows[2]
    nir.data[4, 0] = np.ma.masked  # one pixel without data
    result = compute_indices(*windows)
    assert (result.ndvi_pixels, result.ndmi_pixels) == (36 - 4 - 6 - 1, 8)
    assert (result.ndvi, result.ndmi) == (pytest.approx(0.5), pytest.approx(0.2))


def test_each_index_needs_its_own_eight_pixels():
    assert params.MIN_PIXELS == 8
    seven_fine = np.zeros((6, 6), dtype=bool)
    seven_fine[0, :6] = True
    seven_fine[1, 0] = True
    only_ndmi = compute_indices(*scene(fine_inside=seven_fine))
    assert (only_ndmi.ndvi, only_ndmi.ndvi_pixels) == (None, 7)
    assert only_ndmi.ndmi == pytest.approx(0.2)
    seven_coarse = np.ones((3, 3), dtype=bool)
    seven_coarse[2, 1:] = False
    only_ndvi = compute_indices(*scene(coarse_inside=seven_coarse))
    assert (only_ndvi.ndmi, only_ndvi.ndmi_pixels) == (None, 7)
    assert only_ndvi.ndvi == pytest.approx(0.5)
    eight = seven_coarse.copy()
    eight[2, 1] = True
    assert compute_indices(*scene(coarse_inside=eight)).ndmi == pytest.approx(0.2)


def test_bands_that_were_not_read_give_no_index():
    scl, red, nir, _, _ = scene()
    result = compute_indices(scl, red, nir, None, None)
    assert (result.ndvi, result.ndmi, result.ndmi_pixels) == (pytest.approx(0.5), None, 0)


def test_reflectance_offset_enters_the_indices():
    windows = scene(red=2000, nir=4000, nir08=4000, swir=3000)
    result = compute_indices(*windows, -0.1)
    assert result.ndvi == pytest.approx((0.3 - 0.1) / (0.3 + 0.1))
    assert result.ndmi == pytest.approx((0.3 - 0.2) / (0.3 + 0.2))


@pytest.mark.parametrize("band", ["red", "nir", "nir08", "swir"])
def test_scene_whose_median_reflectance_is_not_positive_is_rejected(band):
    # Stored 1000 with the shift of -1000 is reflectance 0: the shift does not fit the file.
    values = {"red": 2000, "nir": 4000, "nir08": 4000, "swir": 3000, band: 1000}
    with pytest.raises(SceneReadError):
        compute_indices(*scene(**values), -0.1)
    compute_indices(*scene(**values), 0.0)  # the same values without the shift are fine


def test_file_that_cannot_be_opened_is_a_scene_read_error(tmp_path):
    broken = tmp_path / "broken.tif"
    broken.write_bytes(b"not a raster")
    files = SceneFiles(tmp_path)
    files._paths["https://example.invalid/broken.tif"] = broken
    with pytest.raises(SceneReadError):
        read_layer(files.opener, "https://example.invalid/broken.tif", GEOMETRY, buffer_m=5.0)
