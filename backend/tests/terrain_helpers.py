"""Helpers for the terrain tests: synthetic elevation grids on a geographic grid.

The grids copy the shape of the real source: degrees, cells of 1.5 by 1 arc
second (about 28 by 31 m at the latitude of Poland), rows from north to south.
"""

import math
from collections.abc import Callable

from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import TerrainData
from app.engine.terrain_grid import metres_per_degree

LAT, LON = 52.75, 18.2
CELL_LON, CELL_LAT = 1.5 / 3600, 1.0 / 3600
EAST_M, NORTH_M = metres_per_degree(LAT)

Surface = Callable[[float, float], float | None]


def rectangle(width_m: float, height_m: float, lon: float = LON, lat: float = LAT) -> GeoJsonGeometry:
    """Rectangular outline centred on the point, sides given in metres."""
    half_lon, half_lat = width_m / 2 / EAST_M, height_m / 2 / NORTH_M
    ring = [
        [lon - half_lon, lat - half_lat], [lon + half_lon, lat - half_lat],
        [lon + half_lon, lat + half_lat], [lon - half_lon, lat + half_lat],
        [lon - half_lon, lat - half_lat],
    ]
    return GeoJsonGeometry(type="Polygon", coordinates=[ring])


def plane(slope_pct: float, downhill_azimuth_deg: float, base_m: float = 100.0) -> Surface:
    """Elevation of a tilted plane; positions in metres east and north of the centre."""
    azimuth = math.radians(downhill_azimuth_deg)
    fall = slope_pct / 100.0
    return lambda x, y: base_m - fall * (x * math.sin(azimuth) + y * math.cos(azimuth))


def grid(
    surface: Surface,
    *,
    half_cols: int = 6,
    half_rows: int = 6,
    shift_cells: tuple[float, float] = (0.0, 0.0),
    digits: int | None = 2,
) -> TerrainData:
    """A grid around the centre point, `half_*` cells to each side.

    `shift_cells` moves the grid origin by a part of a cell, east and north.
    Elevations are rounded to centimetres like the real source unless
    `digits` is None.
    """
    west = LON - half_cols * CELL_LON + shift_cells[0] * CELL_LON
    north = LAT + half_rows * CELL_LAT + shift_cells[1] * CELL_LAT
    rows = []
    for row in range(2 * half_rows):
        values = []
        for col in range(2 * half_cols):
            x = (west + (col + 0.5) * CELL_LON - LON) * EAST_M
            y = (north - (row + 0.5) * CELL_LAT - LAT) * NORTH_M
            value = surface(x, y)
            values.append(value if value is None or digits is None else round(value, digits))
        rows.append(values)
    return TerrainData(
        resolution_m=30.0,
        crs="EPSG:4326",
        transform=(CELL_LON, 0.0, west, 0.0, -CELL_LAT, north),
        elevations_m=rows,
    )


# About 2 ha: 7 by 4-5 cells inside.
FIELD = rectangle(200.0, 140.0)
