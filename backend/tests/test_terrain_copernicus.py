"""Copernicus DEM link of the terrain chain: recorded catalogue answers, generated raster."""

import asyncio
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from app.contracts.common import GeoJsonGeometry
from app.sources import terrain_params as params
from app.sources.terrain import TerrainLinkError, TerrainSource
from app.sources.terrain_copernicus import CopernicusDem30, elevation_rows, tile_from_search

FIXTURES = Path(__file__).parent / "fixtures" / "earth_search"
TILE_HREF = (
    "s3://copernicus-dem-30m/Copernicus_DSM_COG_10_N52_00_E018_00_DEM/"
    "Copernicus_DSM_COG_10_N52_00_E018_00_DEM.tif"
)

# A piece of a tile on the grid of the product north of 50 degrees:
# 1.5 arc seconds in longitude, 1 arc second in latitude.
WEST, NORTH = 18.19, 52.76
DX, DY = 1.5 / 3600, 1.0 / 3600
COLS, ROWS = 60, 80  # reaches to 18.215 E and about 52.7378 N
NODATA = -32767.0

PARCEL = box(18.1995, 52.7483, 18.2025, 52.7503)  # about 200 m by 220 m


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def plane(rows: int = ROWS, cols: int = COLS) -> np.ndarray:
    """Elevations falling to the south-east: 100 m minus 0.5 per row and 0.25 per column."""
    row, col = np.mgrid[0:rows, 0:cols]
    return (100.0 - 0.5 * row - 0.25 * col).astype("float32")


@pytest.fixture
def tile_path(tmp_path):
    def write(values: np.ndarray, west: float = WEST, north: float = NORTH) -> Path:
        path = tmp_path / "tile.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=values.shape[0],
            width=values.shape[1],
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(west, north, DX, DY),
            nodata=NODATA,
        ) as dst:
            dst.write(values, 1)
        return path

    return write


def source_for(path, payload=None, status=200, seen=None, opened=None) -> TerrainSource:
    """Chain with the single 30 m link: recorded catalogue, local file as the tile."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload or recorded("cop_dem_search_one.json"))

    def open_local(href: str):
        if opened is not None:
            opened.append(href)
        return rasterio.open(path)

    link = CopernicusDem30(transport=httpx.MockTransport(handler), open_dataset=open_local)
    return TerrainSource(links=[link])


def test_recorded_catalogue_answer_gives_tile_address():
    assert tile_from_search(recorded("cop_dem_search_one.json")) == TILE_HREF


def test_empty_catalogue_answer_means_no_coverage():
    with pytest.raises(TerrainLinkError, match="nie obejmuje"):
        tile_from_search(recorded("cop_dem_search_none.json"))


@pytest.mark.parametrize("href", ["s3://other-bucket/tile.tif", "/etc/passwd", None])
def test_address_outside_the_public_bucket_is_refused(href):
    payload = recorded("cop_dem_search_one.json")
    payload["features"][0]["assets"]["data"]["href"] = href
    with pytest.raises(TerrainLinkError):
        tile_from_search(payload)


@pytest.mark.parametrize("payload", [{}, {"features": [{}]}, [], "text"])
def test_unreadable_catalogue_answer_is_a_link_error(payload):
    with pytest.raises(TerrainLinkError):
        tile_from_search(payload)


def test_missing_and_non_finite_cells_become_none():
    data = np.ma.masked_values(np.array([[1.234, NODATA], [np.nan, 4.0]], dtype="float32"), NODATA)
    assert elevation_rows(data) == [[1.23, None], [None, 4.0]]


def test_grid_around_the_parcel(tile_path):
    seen, opened = [], []
    source = source_for(tile_path(plane()), seen=seen, opened=opened)
    data, outcome = asyncio.run(source.fetch(PARCEL))

    assert outcome.ok and outcome.topic == "terrain" and outcome.chain_step == 1
    assert outcome.source_name == params.COPERNICUS_SOURCE_NAME
    assert outcome.data_date == "2011/2015" and outcome.message is None
    assert opened == [TILE_HREF]

    assert data.resolution_m == 30.0 and data.crs == "EPSG:4326"
    a, b, c, d, e, f = data.transform
    assert (a, b, d, e) == pytest.approx((DX, 0.0, 0.0, -DY))
    rows, cols = len(data.elevations_m), len(data.elevations_m[0])
    # The grid covers the parcel and reaches about one cell further on each side.
    west, south, east, north = PARCEL.bounds
    assert c < west and f > north and c + cols * a > east and f + rows * e < south
    assert 0 < (west - c) / DX <= 3 and 0 < (f - north) / DY <= 3
    # Values come from the same cells of the tile, rows from north to south.
    col0, row0 = round((c - WEST) / DX), round((NORTH - f) / DY)
    expected = plane()[row0 : row0 + rows, col0 : col0 + cols]
    assert np.allclose(np.array(data.elevations_m, dtype=float), expected, atol=0.006)


def test_only_coordinates_are_sent_to_the_catalogue(tile_path):
    seen = []
    asyncio.run(source_for(tile_path(plane()), seen=seen).fetch(PARCEL))
    (request,) = seen
    assert request.method == "POST" and str(request.url) == params.COPERNICUS_SEARCH_URL
    assert request.headers["user-agent"] == params.USER_AGENT
    centre = PARCEL.centroid
    assert json.loads(request.content) == {
        "collections": ["cop-dem-glo-30"],
        "intersects": {"type": "Point", "coordinates": [round(centre.x, 6), round(centre.y, 6)]},
        "limit": 1,
    }


def test_outline_may_be_a_contract_geometry(tile_path):
    geometry = GeoJsonGeometry.model_validate(mapping(PARCEL))
    data, outcome = asyncio.run(source_for(tile_path(plane())).fetch(geometry))
    assert outcome.ok and data is not None


def test_cells_without_data_stay_empty(tile_path):
    values = plane()
    values[:, :30] = NODATA  # western half; the parcel lies across column 30
    data, outcome = asyncio.run(source_for(tile_path(values)).fetch(PARCEL))
    cells = [value for row in data.elevations_m for value in row]
    assert outcome.ok and None in cells and any(value is not None for value in cells)


def test_tile_without_values_over_the_parcel_gives_no_data(tile_path):
    values = np.full((ROWS, COLS), NODATA, dtype="float32")
    data, outcome = asyncio.run(source_for(tile_path(values)).fetch(PARCEL))
    assert data is None and not outcome.ok and outcome.chain_step is None
    assert "nie ma wartości" in outcome.message


def test_parcel_across_the_tile_edge_is_reported(tile_path):
    # The tile starts at 18.2005 E, inside the parcel.
    path = tile_path(plane(), west=18.2005)
    data, outcome = asyncio.run(source_for(path).fetch(PARCEL))
    assert outcome.ok and data.transform[2] == pytest.approx(18.2005)
    assert "granicy arkuszy" in outcome.message


def test_parcel_outside_the_tile_gives_no_data(tile_path):
    elsewhere = box(20.0, 50.0, 20.002, 50.002)
    data, outcome = asyncio.run(source_for(tile_path(plane())).fetch(elsewhere))
    assert data is None and not outcome.ok and outcome.source_name is None
    assert outcome.message.startswith("Nie udało się pobrać danych o ukształtowaniu terenu.")


@pytest.mark.parametrize(
    ("payload", "status", "fragment"),
    [
        (None, 503, "katalog"),
        ({"features": "broken"}, 200, "katalog"),
        (recorded("cop_dem_search_none.json"), 200, "nie obejmuje"),
    ],
)
def test_catalogue_failures_give_no_data(tile_path, payload, status, fragment):
    opened = []
    source = source_for(tile_path(plane()), payload=payload, status=status, opened=opened)
    data, outcome = asyncio.run(source.fetch(PARCEL))
    assert data is None and not outcome.ok and fragment in outcome.message
    assert opened == []


def test_unreadable_tile_gives_no_data():
    def broken(href):
        raise RasterioIOError("no such file")

    def handler(request):
        return httpx.Response(200, json=recorded("cop_dem_search_one.json"))

    link = CopernicusDem30(transport=httpx.MockTransport(handler), open_dataset=broken)
    data, outcome = asyncio.run(TerrainSource(links=[link]).fetch(PARCEL))
    assert data is None and not outcome.ok and "odczytać pliku" in outcome.message


def test_production_chain_has_the_30_m_link_only():
    (link,) = TerrainSource()._links
    assert isinstance(link, CopernicusDem30) and link.timeout_s == params.COPERNICUS_LINK_TIMEOUT_S
