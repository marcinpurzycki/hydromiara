"""Raster window reading on small rasters generated in the test, no network."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box, mapping

from app.contracts.common import GeoJsonGeometry
from app.sources import raster

UTM = "EPSG:32634"
WEST, NORTH = 500_000.0, 5_800_000.0  # upper left corner of the projected raster
PIXEL = 10.0
SIZE = 40
NODATA = -9999.0


def _write(path, bands, crs, transform):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=bands.shape[1],
        width=bands.shape[2],
        count=bands.shape[0],
        dtype=bands.dtype,
        crs=crs,
        transform=transform,
        nodata=NODATA,
    ) as dst:
        dst.write(bands)
    return path


def _grid_values(size=SIZE):
    rows, cols = np.mgrid[0:size, 0:size]
    return (rows * 100 + cols).astype("float32")


@pytest.fixture
def utm_path(tmp_path):
    """40 x 40 pixels of 10 m; band 1 holds row * 100 + col, band 2 its negative."""
    first = _grid_values()
    first[0:5, 0:5] = NODATA
    bands = np.stack([first, -_grid_values()])
    return _write(tmp_path / "utm.tif", bands, UTM, from_origin(WEST, NORTH, PIXEL, PIXEL))


@pytest.fixture
def geographic_path(tmp_path):
    """50 x 50 pixels of 0.001 degree in EPSG:4326, upper left at 21 E, 52.05 N."""
    bands = _grid_values(50)[np.newaxis]
    return _write(tmp_path / "geo.tif", bands, raster.WGS84, from_origin(21.0, 52.05, 0.001, 0.001))


def utm_box(col_start, row_start, col_stop, row_stop):
    """Rectangle given by pixel edges of the projected raster, in its CRS."""
    return box(
        WEST + col_start * PIXEL,
        NORTH - row_stop * PIXEL,
        WEST + col_stop * PIXEL,
        NORTH - row_start * PIXEL,
    )


def read(path, geometry, **kwargs):
    with rasterio.open(path) as dataset:
        return raster.read_window(dataset, geometry, **kwargs)


def test_window_covers_exactly_the_outline(utm_path):
    result = read(utm_path, utm_box(10, 20, 20, 30), geometry_crs=UTM, inward_buffer_m=0)

    assert result.data.shape == (10, 10)
    assert result.data[0, 0] == 2010 and result.data[9, 9] == 2919
    assert result.transform == pytest.approx((10.0, 0.0, WEST + 100, 0.0, -10.0, NORTH - 200))
    assert result.crs == UTM
    assert result.resolution == (10.0, 10.0)
    assert result.inside.all()
    assert result.empty_reason is None


def test_window_grows_with_margin_and_snaps_to_whole_pixels(utm_path):
    outline = utm_box(10.4, 20.4, 19.6, 29.6)

    snapped = read(utm_path, outline, geometry_crs=UTM, inward_buffer_m=0)
    wider = read(utm_path, outline, geometry_crs=UTM, inward_buffer_m=0, margin_m=20)

    assert snapped.data.shape == (10, 10)
    assert wider.data.shape == (14, 14)
    assert wider.data[0, 0] == 1808
    # The margin widens the window, not the outline.
    assert wider.inside_count == snapped.inside_count == 100


def test_inward_buffer_drops_pixels_near_the_boundary(utm_path):
    result = read(utm_path, utm_box(10, 20, 20, 30), geometry_crs=UTM, inward_buffer_m=10)

    expected = np.zeros((10, 10), dtype=bool)
    expected[1:9, 1:9] = True
    assert np.array_equal(result.inside, expected)
    assert result.values().min() == 2111 and result.values().max() == 2818


def test_default_inward_buffer_is_applied(utm_path):
    result = read(utm_path, utm_box(10, 20, 20, 30), geometry_crs=UTM)

    assert raster.DEFAULT_INWARD_BUFFER_M == 10.0
    assert result.inside_count == 64


def test_outline_in_wgs84_is_converted_to_the_raster_crs(utm_path):
    outline = raster.reproject_geometry(utm_box(10, 20, 20, 30), UTM, raster.WGS84)
    assert 21 <= outline.centroid.x <= 21.1 and 52.3 <= outline.centroid.y <= 52.4

    as_shape = read(utm_path, outline, inward_buffer_m=5)
    as_geojson = read(utm_path, mapping(outline), inward_buffer_m=5)

    # Edge pixel centres lie 5 m from the boundary and fall out; the next ring stays.
    assert as_shape.data.shape in ((10, 10), (11, 11), (12, 12))
    assert as_shape.inside_count == 64
    assert sorted(as_shape.values())[0] == 2111
    assert np.array_equal(as_shape.inside, as_geojson.inside)
    as_contract = read(utm_path, GeoJsonGeometry(**mapping(outline)), inward_buffer_m=5)
    assert np.array_equal(as_shape.inside, as_contract.inside)


def test_reprojection_uses_longitude_latitude_order():
    # PL-1992: central meridian 19 E maps to easting 500 000 m.
    point = raster.reproject_geometry(Point(19.0, 52.0), raster.WGS84, raster.METRIC_CRS)

    assert point.x == pytest.approx(500_000.0, abs=0.01)
    assert 450_000 < point.y < 470_000


def test_buffer_in_metres_on_geographic_coordinates():
    outline = box(21.0, 52.0, 21.01, 52.01)

    grown = raster.buffer_metres(outline, raster.WGS84, 100)
    shrunk = raster.buffer_metres(outline, raster.WGS84, -100)

    # 100 m is about 0.0009 degree of latitude and 0.0015 degree of longitude here.
    assert grown.bounds[3] - 52.01 == pytest.approx(0.0009, abs=0.0001)
    assert 21.0 - grown.bounds[0] == pytest.approx(0.00146, abs=0.0001)
    assert shrunk.bounds[1] - 52.0 == pytest.approx(0.0009, abs=0.0001)
    assert raster.buffer_metres(outline, raster.WGS84, 0) is outline


def test_geographic_raster_with_buffer_in_metres(geographic_path):
    # Pixels are about 68 m wide and 111 m high at this latitude.
    outline = box(21.01, 52.02, 21.02, 52.03)

    loose = read(geographic_path, outline, inward_buffer_m=10)
    tight = read(geographic_path, outline, inward_buffer_m=70)

    assert loose.data.shape == (10, 10)
    assert loose.data[0, 0] == 2010
    assert loose.crs == raster.WGS84
    assert loose.inside_count == 100
    expected = np.zeros((10, 10), dtype=bool)
    expected[1:9, 1:9] = True
    assert np.array_equal(tight.inside, expected)


def test_parcel_smaller_than_a_pixel_gives_empty_mask(utm_path):
    sliver = utm_box(10.1, 20.1, 10.4, 20.4)

    result = read(utm_path, sliver, geometry_crs=UTM, inward_buffer_m=0)

    assert result.data.shape == (1, 1)
    assert result.inside_count == 0
    assert result.values().size == 0
    assert result.empty_reason == "parcel_too_small"


def test_parcel_consumed_by_the_inward_buffer_gives_empty_mask(utm_path):
    result = read(utm_path, utm_box(10, 20, 13, 23), geometry_crs=UTM, inward_buffer_m=20)

    assert result.data.shape == (3, 3)
    assert not result.inside.any()
    assert result.empty_reason == "parcel_too_small"


def test_parcel_outside_the_raster(utm_path):
    result = read(utm_path, utm_box(60, 60, 70, 70), geometry_crs=UTM, inward_buffer_m=0)

    assert result.data.shape == (0, 0)
    assert result.inside.shape == (0, 0)
    assert result.empty_reason == "outside_raster"


def test_window_is_clipped_to_the_raster_edge(utm_path):
    result = read(utm_path, utm_box(35, 35, 45, 45), geometry_crs=UTM, inward_buffer_m=0)

    assert result.data.shape == (5, 5)
    assert result.data[0, 0] == 3535
    assert result.inside.all()


def test_pixels_without_data_are_not_valid(utm_path):
    partly = read(utm_path, utm_box(0, 0, 10, 10), geometry_crs=UTM, inward_buffer_m=0)
    fully = read(utm_path, utm_box(0, 0, 5, 5), geometry_crs=UTM, inward_buffer_m=0)

    assert partly.inside_count == 100
    assert int(partly.valid.sum()) == 75
    assert NODATA not in partly.values()
    assert partly.empty_reason is None
    assert fully.inside_count == 25
    assert fully.empty_reason == "no_valid_data"


def test_band_selection(utm_path):
    result = read(utm_path, utm_box(10, 20, 12, 22), geometry_crs=UTM, inward_buffer_m=0, band=2)

    assert result.values().tolist() == [-2010, -2011, -2110, -2111]


def test_geometry_window_and_outline_mask_work_on_their_own(utm_path):
    with rasterio.open(utm_path) as dataset:
        window = raster.geometry_window(dataset, utm_box(2, 3, 6, 5))
        transform = dataset.window_transform(window)
        assert (window.col_off, window.row_off, window.width, window.height) == (2, 3, 4, 2)
        assert raster.geometry_window(dataset, utm_box(-9, -9, -1, -1)) is None
        assert raster.geometry_window(dataset, box(0, 0, 1, 1).buffer(-1)) is None

    left_half = raster.outline_mask(utm_box(2, 3, 4, 5), (2, 4), transform)
    assert left_half.tolist() == [[True, True, False, False]] * 2
    assert not raster.outline_mask(box(0, 0, 1, 1).buffer(-1), (2, 4), transform).any()


@pytest.mark.parametrize("bad", [Point(21.0, 52.0), box(0, 0, 1, 1).buffer(-1)])
def test_outline_must_be_a_polygon(utm_path, bad):
    with pytest.raises(ValueError):
        read(utm_path, bad)


@pytest.mark.parametrize("kwargs", [{"inward_buffer_m": -1}, {"margin_m": -1}])
def test_distances_must_not_be_negative(utm_path, kwargs):
    with pytest.raises(ValueError):
        read(utm_path, utm_box(10, 20, 20, 30), geometry_crs=UTM, **kwargs)
