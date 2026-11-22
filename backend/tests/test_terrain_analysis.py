"""Terrain analysis on synthetic grids shaped like the real source (degrees, 1.5 x 1 arcsec)."""

import math
import random

import pytest

from app.contracts.common import GeoJsonGeometry
from app.engine.cause_params import CauseParams
from app.engine.terrain_analysis import analyse_terrain, azimuth_of, compass_index
from app.engine.terrain_grid import metres_per_degree, parcel_cells
from tests.terrain_helpers import FIELD, LAT, grid, plane, rectangle


def test_ground_distances_follow_the_latitude_not_the_nominal_resolution():
    east, north = metres_per_degree(LAT)
    # One degree of latitude is about 111 km; of longitude it shrinks with cos(latitude).
    assert north == pytest.approx(111_270, abs=50)
    assert east == pytest.approx(north * math.cos(math.radians(LAT)), rel=0.005)
    cells = parcel_cells(grid(plane(0, 0)), FIELD)
    width, height = cells.cell_size_m
    assert width == pytest.approx(28.1, abs=0.1) and height == pytest.approx(30.9, abs=0.1)


@pytest.mark.parametrize(
    "azimuth, label, lowest",
    [
        (0, "północ", "północna"),
        (90, "wschód", "wschodnia"),
        (180, "południe", "południowa"),
        (270, "zachód", "zachodnia"),
        (45, "północny wschód", None),
        (135, "południowy wschód", None),
        (225, "południowy zachód", None),
        (315, "północny zachód", None),
        (30, "północny wschód", None),
    ],
)
def test_plane_of_known_slope_and_direction(azimuth, label, lowest):
    result = analyse_terrain(grid(plane(3.0, azimuth)), FIELD)
    assert result.status == "ok" and result.direction_resolved
    assert result.slope_pct == pytest.approx(3.0, abs=0.02)
    assert result.downhill_azimuth_deg == pytest.approx(azimuth, abs=0.5)
    assert result.downhill_label == label
    if lowest is not None:
        assert result.lowest_part == lowest


def test_lowest_part_of_a_square_parcel_lies_in_the_downhill_corner():
    result = analyse_terrain(grid(plane(3.0, 225)), rectangle(200.0, 200.0))
    assert result.lowest_part == "południowo-zachodnia"


def test_a_hollow_in_the_middle_is_the_lowest_part():
    def surface(x, y):
        return 100.0 - 0.005 * x - 6.0 * math.exp(-(x * x + y * y) / 5000.0)

    # The hollow hides the gentle slope, so nothing is said by default.
    assert analyse_terrain(grid(surface), rectangle(200.0, 200.0)).lowest_part is None
    params = CauseParams(slope_min_signal_to_error=0.01)
    result = analyse_terrain(grid(surface), rectangle(200.0, 200.0), params)
    assert result.lowest_part == "środkowa" and result.relief_m > 3.0


def test_cells_of_equal_height_all_count_as_the_lowest_part():
    # Two rows of four cells falling south: the whole southern row is the lowest part.
    result = analyse_terrain(grid(plane(4.0, 180)), rectangle(86.0, 62.0))
    assert result.cells_used == 8 and result.lowest_part == "południowa"


def test_result_does_not_depend_on_the_margin_outside_the_outline():
    narrow = analyse_terrain(grid(plane(2.5, 60), half_cols=5, half_rows=4), FIELD)
    wide = analyse_terrain(grid(plane(2.5, 60), half_cols=12, half_rows=11), FIELD)
    assert narrow.cells_used == wide.cells_used
    assert narrow.slope_pct == pytest.approx(wide.slope_pct, abs=1e-9)
    assert narrow.downhill_azimuth_deg == pytest.approx(wide.downhill_azimuth_deg, abs=1e-6)
    assert narrow.lowest_part == wide.lowest_part

    # A cliff right outside the outline changes nothing.
    def with_cliff(x, y):
        return plane(2.5, 60)(x, y) + (50.0 if abs(x) > 100.0 or abs(y) > 70.0 else 0.0)

    cliff = analyse_terrain(grid(with_cliff, half_cols=12, half_rows=11), FIELD)
    assert cliff.slope_pct == pytest.approx(wide.slope_pct, abs=1e-9)


def test_cells_without_a_value_are_left_out():
    def holes(x, y):
        return None if (x > 40.0 and y > 20.0) else plane(3.0, 90)(x, y)

    result = analyse_terrain(grid(holes), FIELD)
    assert result.status == "ok"
    assert 0 < result.cells_used < result.cells_inside
    assert result.slope_pct == pytest.approx(3.0, abs=0.02)
    assert result.downhill_label == "wschód"


def test_grid_covering_part_of_the_parcel_is_analysed_and_flagged():
    whole = analyse_terrain(grid(plane(3.0, 90)), FIELD)
    part = analyse_terrain(grid(plane(3.0, 90), half_cols=2), FIELD)
    assert whole.covers_parcel and not part.covers_parcel
    assert part.status == "ok" and part.cells_used < whole.cells_used
    assert part.slope_pct == pytest.approx(3.0, abs=0.03)


@pytest.mark.parametrize(
    "outline",
    [
        pytest.param(rectangle(40.0, 40.0), id="tiny-parcel"),
        pytest.param(rectangle(300.0, 20.0), id="one-row-strip"),
        pytest.param(GeoJsonGeometry(type="Point", coordinates=[18.2, 52.75]), id="not-a-polygon"),
    ],
)
def test_too_few_cells_is_said_instead_of_a_slope(outline):
    result = analyse_terrain(grid(plane(5.0, 90), shift_cells=(0.0, 0.3)), outline)
    assert result.status == "too_few_cells"
    assert result.slope_pct is None and result.downhill_label is None
    assert result.lowest_part is None


def test_cells_in_one_line_do_not_give_a_slope():
    # A strip one cell wide and eight cells long: enough cells, but in one line.
    result = analyse_terrain(grid(plane(5.0, 90), shift_cells=(0.0, 0.5)), rectangle(230.0, 20.0))
    assert result.cells_used >= 6 and result.status == "too_few_cells"


def test_grid_of_exactly_the_minimum_is_analysed():
    terrain = grid(plane(4.0, 180), shift_cells=(0.5, 0.0))
    result = analyse_terrain(terrain, rectangle(80.0, 62.0))
    assert result.cells_used == 6 and result.status == "ok"
    assert result.slope_pct == pytest.approx(4.0, abs=0.05)
    assert result.downhill_label == "południe"


def test_flat_terrain_has_no_direction():
    result = analyse_terrain(grid(plane(0.0, 0)), FIELD)
    assert result.status == "ok" and result.slope_pct == 0.0
    assert not result.direction_resolved
    assert result.downhill_azimuth_deg is None and result.lowest_part is None


def test_slope_below_the_scatter_of_the_data_is_not_given_a_direction():
    noise = random.Random(7)

    def rough(x, y):
        return plane(0.2, 90)(x, y) + noise.uniform(-1.0, 1.0)

    small = rectangle(120.0, 100.0)
    result = analyse_terrain(grid(rough), small)
    assert result.status == "ok" and not result.direction_resolved
    assert result.slope_error_pct > 0.2
    assert result.downhill_label is None and result.lowest_part is None
    # The same scatter does not hide a steep slope.
    steep = analyse_terrain(grid(lambda x, y: rough(x, y) + plane(8.0, 90, 0.0)(x, y)), small)
    assert steep.direction_resolved and steep.downhill_label == "wschód"


def test_grid_that_is_not_geographic_is_not_analysed():
    terrain = grid(plane(3.0, 90)).model_copy(update={"crs": "EPSG:2180"})
    assert analyse_terrain(terrain, FIELD).status == "unsupported_grid"


def test_compass_sectors():
    assert [compass_index(a) for a in (0, 22.4, 22.6, 337.4, 337.6, 359.9)] == [0, 0, 1, 7, 0, 0]
    assert azimuth_of(1.0, 0.0) == pytest.approx(90.0)
    assert azimuth_of(-1.0, -1.0) == pytest.approx(225.0)


def test_analysis_is_deterministic():
    assert analyse_terrain(grid(plane(2.2, 200)), FIELD) == analyse_terrain(
        grid(plane(2.2, 200)), FIELD
    )
