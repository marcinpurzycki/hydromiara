"""Terrain analysis on a metric grid (PL-1992) and its agreement with a geographic one."""

import dataclasses

import pytest

from app.contracts.report import Report
from app.engine.terrain_analysis import analyse_terrain
from app.engine.terrain_grid import grid_north_azimuth_deg, parcel_cells
from app.engine.terrain_report import terrain_limitations
from app.sources.raster import WGS84, reproject_geometry
from app.sources.terrain import TerrainSource
from app.sources.terrain_gugik import GugikPointHeights, point_grid
from app.sources.terrain_params import COPERNICUS_SOURCE_NAME, GUGIK_SOURCE_NAME
from tests.analysis_helpers import start, wait_finished
from tests.point_height_helpers import PointService, expected_convergence_deg, metric_grid
from tests.terrain_helpers import FIELD, LAT, grid, plane, rectangle
from tests.test_report_causes import build, data_with, texts
from tests.test_terrain_chain import FakeLink

EAST_LON = 23.5  # far from the central meridian of PL-1992: grid north is 3.6 degrees off


def turn_between(azimuth_a: float, azimuth_b: float) -> float:
    """Smallest angle between two azimuths, degrees."""
    return abs((azimuth_a - azimuth_b + 180.0) % 360.0 - 180.0)


@pytest.mark.parametrize("azimuth", [0, 45, 90, 135, 180, 225, 270, 315, 30])
def test_plane_of_known_slope_and_direction_on_a_metric_grid(azimuth):
    result = analyse_terrain(metric_grid(plane(3.0, azimuth), digits=None), FIELD)
    assert result.status == "ok" and result.direction_resolved and result.covers_parcel
    assert result.cell_size_m == (5.0, 5.0)
    assert result.slope_pct == pytest.approx(3.0, abs=0.01)
    assert turn_between(result.downhill_azimuth_deg, azimuth) < 0.1


@pytest.mark.parametrize("azimuth", [0, 90, 200, 315])
def test_direction_is_given_from_true_north_where_grid_north_differs(azimuth):
    field = rectangle(200.0, 140.0, lon=EAST_LON)
    terrain = metric_grid(plane(3.0, azimuth), lon=EAST_LON, digits=None)
    turn = grid_north_azimuth_deg(*terrain.transform[2:6:3])
    assert turn == pytest.approx(expected_convergence_deg(EAST_LON, LAT), abs=0.05)
    assert abs(turn) > 3.5
    result = analyse_terrain(terrain, field)
    assert turn_between(result.downhill_azimuth_deg, azimuth) < 0.1
    assert result.slope_pct == pytest.approx(3.0, abs=0.01)


@pytest.mark.parametrize("azimuth, lowest", [(0, "północna"), (135, None), (250, "zachodnia")])
def test_metric_and_geographic_grid_of_one_surface_agree(azimuth, lowest):
    def surface(x, y):  # a tilted plane with a gentle wave, the same ground for both grids
        return plane(2.5, azimuth)(x, y) + 0.3 * ((x / 100.0) ** 2 - (y / 80.0) ** 2)

    fine = analyse_terrain(metric_grid(surface), FIELD)
    coarse = analyse_terrain(grid(surface), FIELD)
    assert fine.cells_used > 30 * coarse.cells_used
    assert fine.slope_pct == pytest.approx(coarse.slope_pct, abs=0.15)
    assert turn_between(fine.downhill_azimuth_deg, coarse.downhill_azimuth_deg) < 3.0
    assert fine.downhill_label == coarse.downhill_label
    if lowest is not None:
        assert fine.lowest_part == coarse.lowest_part == lowest


def test_cells_without_a_height_are_left_out_of_a_metric_grid():
    def holes(x, y):
        return None if (x > 40.0 and y > 20.0) else plane(3.0, 90)(x, y)

    result = analyse_terrain(metric_grid(holes), FIELD)
    assert result.status == "ok" and 0 < result.cells_used < result.cells_inside
    assert result.slope_pct == pytest.approx(3.0, abs=0.02) and result.downhill_label == "wschód"
    empty = analyse_terrain(metric_grid(lambda x, y: None), FIELD)
    assert empty.status == "too_few_cells" and empty.cells_used == 0 and empty.cells_inside > 0


def test_metric_grid_covering_part_of_the_parcel_is_flagged():
    part = parcel_cells(metric_grid(plane(3.0, 90), half=10), FIELD)
    assert part.supported and not part.covers_outline and part.cells


def test_limitations_name_the_model_that_gave_the_terrain():
    fine = build(data_with(metric_grid(plane(3.0, 45)), terrain_name=GUGIK_SOURCE_NAME))
    assert any("numerycznego modelu terenu GUGiK co 5 m" in text for text in texts(fine))
    assert not any("razem z budynkami" in text or "za wąska" in text for text in texts(fine))
    assert any("średniego spadku całej Działki" in text for text in texts(fine))
    slope = next(entry for entry in fine.trace if entry.rule_id == "terrain.slope")
    assert slope.values["slope_pct"] == 3.0 and slope.values["downhill_azimuth_deg"] == 45

    small = rectangle(100.0, 70.0)  # six to nine cells of the 30 m model
    data = data_with(grid(plane(3.0, 45)), outline=small, terrain_name=COPERNICUS_SOURCE_NAME)
    analysis = analyse_terrain(data.terrain, small)
    assert analysis.analysed and analysis.cells_used < 10
    named = [item.text for item in terrain_limitations(data, analysis)]
    assert any("za mała albo za wąska" in text for text in named)
    assert any("razem z budynkami i roślinnością" in text for text in named)


def _service_over(geometry) -> PointService:
    bounds = reproject_geometry(geometry, WGS84, "EPSG:2180").bounds
    origin = point_grid(bounds)
    # Falls to the north by 3 m per 100 m.
    return PointService(lambda n, e: round(120.0 - 0.03 * (n - origin.north + 400), 1))


def test_whole_analysis_on_point_heights_gives_a_valid_report(client, optional_sources):
    from shapely.geometry import shape

    from tests.analysis_helpers import stored_source_data

    service = _service_over(shape(stored_source_data().parcel.geometry.model_dump()))
    source = TerrainSource(links=[GugikPointHeights(transport=service), FakeLink("unused")])
    optional_sources.current = dataclasses.replace(optional_sources.recorded(), terrain=source)
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    terrain = next(source for source in report.sources if source.topic == "terrain")
    assert terrain.name == GUGIK_SOURCE_NAME and terrain.chain_step == 1 and not terrain.missing
    assert "GUGiK" in terrain.license and "Copernicus" not in terrain.license
    slope = next(entry for entry in report.trace if entry.rule_id == "terrain.slope")
    assert slope.values["slope_pct"] == 3.0 and slope.result == "teren opada na północ"
    assert slope.values["cells_used"] > 500 and service.requests
    assert report.map.downhill_direction.label == "północ"
    assert not any("zamiennika" in item.text for item in report.limitations)


def test_whole_analysis_stepping_down_names_the_substitute(client, optional_sources):
    recorded = optional_sources.recorded()
    failing = GugikPointHeights(transport=PointService(lambda n, e: None))
    source = TerrainSource(links=[failing, *recorded.terrain._links])
    optional_sources.current = dataclasses.replace(recorded, terrain=source)
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    terrain = next(source for source in report.sources if source.topic == "terrain")
    assert terrain.name == COPERNICUS_SOURCE_NAME and terrain.chain_step == 2
    assert "Copernicus" in terrain.license
    named = [item for item in report.limitations if "mniej dokładnego zamiennika" in item.text]
    assert len(named) == 1 and COPERNICUS_SOURCE_NAME in named[0].text
    assert any("razem z budynkami i roślinnością" in item.text for item in report.limitations)
