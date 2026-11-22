"""Cells of an elevation grid that lie inside a parcel outline, in local metres.

Two kinds of grid are read. A geographic grid (degrees, EPSG:4326) has cells
that are not square on the ground, so distances are taken from the affine
transform and the latitude, never from the nominal resolution. A grid in
PL-1992 (EPSG:2180) is metric: distances come straight from the transform.
Its north is not true north, though: grid north turns away from the meridian
by up to about 4 degrees at the eastern and western ends of Poland (meridian
convergence), so positions are rotated to true east and north. The scale of
the projection (0.9993 to about 1.0008 across Poland) is left as it is: it
changes a slope by less than a thousandth of its value.

Positions are metres east and north of the mean position of the kept cells,
which makes the result independent of how far the grid reaches beyond the
outline.

Pure: geometry arithmetic only.
"""

import math
from dataclasses import dataclass

from pyproj import Transformer
from shapely import Point
from shapely import transform as transform_coordinates
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import TerrainData

GEOGRAPHIC_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:2180"
SUPPORTED_CRS = (GEOGRAPHIC_CRS, METRIC_CRS)

# Length of the northward step from which the direction of grid north is taken.
_NORTH_PROBE_M = 100.0

# WGS 84 ellipsoid: semi-major axis in metres and flattening (defining values).
_SEMI_MAJOR_M = 6378137.0
_FLATTENING = 1 / 298.257223563
_ECCENTRICITY_SQ = _FLATTENING * (2 - _FLATTENING)

# Outline bounds may pass the grid edge by this part of a cell and still count
# as covered (floating point noise of the transform).
_EDGE_TOLERANCE_CELLS = 1e-6


def metres_per_degree(latitude_deg: float) -> tuple[float, float]:
    """(metres per degree of longitude, per degree of latitude) on the ellipsoid.

    From the radii of curvature of the ellipsoid at the latitude: the prime
    vertical radius N for longitude and the meridian radius M for latitude.
    """
    phi = math.radians(latitude_deg)
    w = math.sqrt(1 - _ECCENTRICITY_SQ * math.sin(phi) ** 2)
    prime_vertical = _SEMI_MAJOR_M / w
    meridian = _SEMI_MAJOR_M * (1 - _ECCENTRICITY_SQ) / w**3
    return math.radians(1) * prime_vertical * math.cos(phi), math.radians(1) * meridian


@dataclass(frozen=True)
class Cell:
    """One grid cell with an elevation; position of its centre in local metres."""

    row: int
    col: int
    x_m: float  # east
    y_m: float  # north
    elevation_m: float


@dataclass(frozen=True)
class ParcelCells:
    """What the grid holds for the parcel."""

    # False when the grid is in a system that is not read; nothing else is filled.
    supported: bool
    # Cells with an elevation whose centre lies inside the outline.
    cells: tuple[Cell, ...] = ()
    # Cell centres inside the outline, with or without an elevation.
    inside_count: int = 0
    # Mean cell width (east-west) and height (north-south) on the ground.
    cell_size_m: tuple[float, float] | None = None
    # False when the outline reaches beyond the grid (e.g. a parcel on the
    # edge of two source tiles), so part of the parcel has no cells at all.
    covers_outline: bool = False


def _centre(transform: tuple[float, ...], row: int, col: int) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    x, y = col + 0.5, row + 0.5
    return a * x + b * y + c, d * x + e * y + f


def _covers(terrain: TerrainData, bounds: tuple[float, float, float, float]) -> bool:
    rows = len(terrain.elevations_m)
    cols = max((len(row) for row in terrain.elevations_m), default=0)
    a, b, c, d, e, f = terrain.transform
    corners = [(a * x + b * y + c, d * x + e * y + f) for x in (0, cols) for y in (0, rows)]
    lons, lats = [x for x, _ in corners], [y for _, y in corners]
    slack_lon = _EDGE_TOLERANCE_CELLS * (abs(a) + abs(b))
    slack_lat = _EDGE_TOLERANCE_CELLS * (abs(d) + abs(e))
    min_lon, min_lat, max_lon, max_lat = bounds
    return (
        min(lons) - slack_lon <= min_lon
        and max_lon <= max(lons) + slack_lon
        and min(lats) - slack_lat <= min_lat
        and max_lat <= max(lats) + slack_lat
    )


def grid_north_azimuth_deg(east_m: float, north_m: float) -> float:
    """Azimuth of grid north of PL-1992 at a point, degrees clockwise from true north."""
    to_geographic = Transformer.from_crs(METRIC_CRS, GEOGRAPHIC_CRS, always_xy=True)
    lon0, lat0 = to_geographic.transform(east_m, north_m)
    lon1, lat1 = to_geographic.transform(east_m, north_m + _NORTH_PROBE_M)
    per_lon, per_lat = metres_per_degree(lat0)
    return math.degrees(math.atan2((lon1 - lon0) * per_lon, (lat1 - lat0) * per_lat))


def _outline_in_grid(outline: GeoJsonGeometry, crs: str) -> BaseGeometry:
    polygon = shape(outline.model_dump())
    if crs == GEOGRAPHIC_CRS or polygon.is_empty:
        return polygon
    to_metric = Transformer.from_crs(GEOGRAPHIC_CRS, METRIC_CRS, always_xy=True)
    return transform_coordinates(polygon, to_metric.transform, interleaved=False)


def parcel_cells(terrain: TerrainData, outline: GeoJsonGeometry) -> ParcelCells:
    """Grid cells whose centre lies inside the parcel outline.

    An outline that is not a polygon has no inside and gives no cells.
    """
    crs = terrain.crs.upper()
    if crs not in SUPPORTED_CRS:
        return ParcelCells(supported=False)
    polygon = _outline_in_grid(outline, crs)
    if polygon.is_empty or polygon.geom_type not in ("Polygon", "MultiPolygon"):
        return ParcelCells(supported=True)

    # Row, column, position in the system of the grid, elevation.
    inside: list[tuple[int, int, float, float, float | None]] = []
    for row, values in enumerate(terrain.elevations_m):
        for col, elevation in enumerate(values):
            x, y = _centre(terrain.transform, row, col)
            if polygon.contains(Point(x, y)):
                inside.append((row, col, x, y, elevation))
    covers = _covers(terrain, polygon.bounds)
    kept = [item for item in inside if item[4] is not None]
    if not kept:
        return ParcelCells(supported=True, inside_count=len(inside), covers_outline=covers)

    x0 = sum(item[2] for item in kept) / len(kept)
    y0 = sum(item[3] for item in kept) / len(kept)
    if crs == GEOGRAPHIC_CRS:
        east_m, north_m = metres_per_degree(y0)
        turn = 0.0
    else:
        east_m, north_m = 1.0, 1.0
        turn = math.radians(grid_north_azimuth_deg(x0, y0))
    cos_turn, sin_turn = math.cos(turn), math.sin(turn)

    def local(x: float, y: float) -> tuple[float, float]:
        """Metres to true east and north of the mean position."""
        dx, dy = (x - x0) * east_m, (y - y0) * north_m
        return dx * cos_turn + dy * sin_turn, dy * cos_turn - dx * sin_turn

    a, b, _, d, e, _ = terrain.transform
    return ParcelCells(
        supported=True,
        cells=tuple(
            Cell(row, col, *local(x, y), elevation) for row, col, x, y, elevation in kept
        ),
        inside_count=len(inside),
        # Length on the ground of one step along a grid row and along a column.
        cell_size_m=(math.hypot(a * east_m, d * north_m), math.hypot(b * east_m, e * north_m)),
        covers_outline=covers,
    )
