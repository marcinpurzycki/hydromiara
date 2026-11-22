"""Point height link: the point grid, requests, reading rules, success threshold."""

import asyncio

import pytest
from shapely.geometry import box

from app.engine.source_limitations import step_down_limitation
from app.sources import terrain_params as params
from app.sources.raster import WGS84, reproject_geometry
from app.sources.terrain import TerrainLinkError, TerrainSource, default_links
from app.sources.terrain_copernicus import CopernicusDem30
from app.sources.terrain_gugik import (
    GugikPointHeights,
    parse_heights,
    point_grid,
    request_url,
    settle,
)
from tests.point_height_helpers import PointService, tilted
from tests.test_terrain_chain import FakeLink, reading

PARCEL = box(18.1995, 52.7483, 18.2025, 52.7503)  # about 200 by 220 m
BOUNDS = reproject_geometry(PARCEL, WGS84, "EPSG:2180").bounds
GRID = point_grid(BOUNDS)
PLANE = tilted(GRID.north, GRID.west)


def read(service: PointService, parcel=PARCEL):
    return asyncio.run(GugikPointHeights(transport=service).read(parcel))


def test_grid_has_whole_metre_points_every_five_metres_within_the_margin():
    grid = point_grid((500_000.4, 600_000.6, 500_100.0, 600_050.0))
    assert (grid.step, grid.west, grid.north) == (5, 499_971, 600_080)
    assert (grid.cols, grid.rows) == (32, 22)  # 159.6 m and 109.4 m of window
    points = grid.points()
    assert points[0] == (600_080, 499_971) and points[1] == (600_080, 499_976)
    assert points[grid.cols] == (600_075, 499_971) and len(points) == 32 * 22
    assert all(499_970.4 <= e <= 500_130 and 599_970.6 <= n <= 600_080 for n, e in points)
    # Every point is the centre of its cell.
    a, _, c, _, e, f = grid.transform
    assert (a * 0.5 + c, e * 0.5 + f) == (499_971, 600_080) and (a, e) == (5.0, -5.0)


def test_large_parcel_gets_a_wider_spacing_within_the_point_limit():
    grid = point_grid((500_000.0, 600_000.0, 500_600.0, 600_400.0))  # 24 ha
    assert grid.step == 9 and grid.cols * grid.rows <= params.GUGIK_MAX_POINTS
    tighter = (660 // (grid.step - 1) + 1) * (460 // (grid.step - 1) + 1)
    assert tighter > params.GUGIK_MAX_POINTS


def test_request_lists_northing_first_and_refuses_more_than_the_service_answers():
    url = request_url([(600_080, 499_971), (600_075, 499_971)])
    assert url == (
        "https://services.gugik.gov.pl/nmt/?request=GetHByPointList"
        "&list=600080%20499971,600075%20499971"
    )
    with pytest.raises(ValueError):
        request_url([(600_000, 500_000)] * 1001)


def test_answer_rows_are_read_in_order_and_a_missing_field_is_no_height():
    assert parse_heights("1 2 85.3,3 4,5 6 0.0", 3) == [85.3, None, 0.0]
    assert parse_heights("1 2 85.3", 2) is None
    assert parse_heights("<html>error</html>", 1) is None
    assert parse_heights("1 2 abc", 1) is None


def test_grid_is_asked_in_batches_by_get_and_returned_north_first():
    service = PointService(PLANE)
    result = read(service)
    data = result.data
    assert (data.crs, data.resolution_m, data.transform) == ("EPSG:2180", 5.0, GRID.transform)
    assert len(data.elevations_m) == GRID.rows and len(data.elevations_m[0]) == GRID.cols
    # Heights rise to the north: the first row is the northernmost.
    assert data.elevations_m[0][0] == 100.0 and data.elevations_m[-1][0] < 99.0
    assert data.elevations_m[2][3] == PLANE(GRID.north - 10, GRID.west + 15)
    total = GRID.cols * GRID.rows
    assert sorted(len(batch) for batch in service.batches)[-1] == params.GUGIK_POINTS_PER_REQUEST
    assert len(service.requests) == -(-total // 400) and sum(map(len, service.batches)) == total
    assert all(request.method == "GET" and not request.content for request in service.requests)
    assert b"%20" in service.requests[0].url.query
    assert result.note is None and result.data_date is None


def test_batch_of_zeros_is_asked_once_more():
    service = PointService(PLANE, faults={0: "zeros", 1: "zeros"})
    data = read(service).data
    batches = -(-GRID.cols * GRID.rows // 400)
    assert len(service.requests) == batches + 2
    assert all(value is not None and value > 0 for row in data.elevations_m for value in row)


def test_batch_of_zeros_twice_gives_no_heights(monkeypatch):
    # One request at a time, so the first batch gets both faulty answers.
    monkeypatch.setattr(params, "GUGIK_PARALLEL_REQUESTS", 1)
    service = PointService(PLANE, faults={0: "zeros", 1: "zeros"})
    heights = asyncio.run(GugikPointHeights(transport=service).heights(GRID.points()[:800]))
    assert heights[:400] == [None] * 400 and None not in heights[400:]
    assert len(service.requests) == 3


def test_zeros_repeated_among_real_heights_are_ground_at_sea_level():
    low = PointService(lambda n, e: 0.0 if (e - GRID.west) % 50 == 0 else 0.4)
    heights = [value for row in read(low).data.elevations_m for value in row]
    assert 0.0 in heights and 0.4 in heights and None not in heights
    assert settle([0.0, 1.0, 0.0, None], [2.0, 1.0, 0.0, 3.0]) == [2.0, 1.0, 0.0, 3.0]
    assert settle([0.0, 1.0], None) == [None, 1.0]
    assert settle(None, [0.0, 0.0]) is None and settle(None, None) is None


def test_failed_request_is_repeated_once():
    assert len(read(PointService(PLANE, faults={0: "error"})).data.elevations_m) == GRID.rows


def test_points_past_the_service_limit_have_no_height():
    service = PointService(PLANE)
    service.limit = 300  # the stand-in answers fewer points, like the service past 1000
    with pytest.raises(TerrainLinkError, match="nie podała wysokości"):
        read(service)


def test_link_succeeds_only_with_nine_tenths_of_the_points_inside():
    metric = reproject_geometry(PARCEL, WGS84, "EPSG:2180")
    centre = metric.centroid

    def with_gap(share: float):
        # A strip across the parcel, `share` of its height, has no heights.
        half = share * (BOUNDS[3] - BOUNDS[1]) / 2
        return PointService(lambda n, e: None if abs(n - centre.y) < half else PLANE(n, e))

    data = read(with_gap(0.08)).data
    assert any(value is None for row in data.elevations_m for value in row)
    with pytest.raises(TerrainLinkError, match="nie podała wysokości"):
        read(with_gap(0.14))


def test_parcel_without_three_points_inside_is_too_small():
    with pytest.raises(TerrainLinkError, match="za mała"):
        read(PointService(PLANE), box(18.2, 52.75, 18.20003, 52.75002))


def test_slow_service_steps_down_to_the_substitute_with_a_limitation():
    link = GugikPointHeights(transport=PointService(PLANE, delay_s=1.0))
    link.timeout_s = 0.05
    coarse = FakeLink(params.COPERNICUS_SOURCE_NAME, reading(30.0))
    data, outcome = asyncio.run(TerrainSource(links=[link, coarse]).fetch(PARCEL))
    assert data.resolution_m == 30.0 and outcome.chain_step == 2 and outcome.duration_s < 0.5
    assert "w wyznaczonym czasie" in outcome.message
    limitation = step_down_limitation(outcome)
    assert limitation is not None and "mniej dokładnego zamiennika" in limitation.text
    assert limitation.affects == "recommendations"


def test_both_links_failing_give_no_data():
    link = GugikPointHeights(transport=PointService(lambda n, e: None))
    coarse = FakeLink(params.COPERNICUS_SOURCE_NAME, error="katalog nie odpowiedział")
    data, outcome = asyncio.run(TerrainSource(links=[link, coarse]).fetch(PARCEL))
    assert data is None and not outcome.ok and outcome.chain_step is None
    assert "nie podała wysokości" in outcome.message and "katalog" in outcome.message


def test_production_chain_asks_the_point_service_first():
    first, second = default_links()
    assert isinstance(first, GugikPointHeights) and isinstance(second, CopernicusDem30)
    assert first.timeout_s == params.GUGIK_LINK_TIMEOUT_S == 8.0
    assert first.name == "Numeryczny model terenu GUGiK w siatce 1 m, odczytany co 5 m"
