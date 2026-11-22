"""Cells of an elevation grid that lie inside a parcel outline, in local metres.

The grid of the source data is geographic (degrees) and its cells are not
square on the ground, so distances are taken from the affine transform and the
latitude, never from the nominal resolution. Positions are metres east and
north of the mean position of the kept cells, which makes the result
independent of how far the grid reaches beyond the outline.

Pure: geometry arithmetic only.
"""

import math
from dataclasses import dataclass

from shapely import Point
from shapely.geometry import shape

from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import TerrainData

SUPPORTED_CRS = "EPSG:4326"

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

    # False when the grid is not geographic; nothing else is filled then.
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
    lons, lats = [lon for lon, _ in corners], [lat for _, lat in corners]
    slack_lon = _EDGE_TOLERANCE_CELLS * (abs(a) + abs(b))
    slack_lat = _EDGE_TOLERANCE_CELLS * (abs(d) + abs(e))
    min_lon, min_lat, max_lon, max_lat = bounds
    return (
        min(lons) - slack_lon <= min_lon
        and max_lon <= max(lons) + slack_lon
        and min(lats) - slack_lat <= min_lat
        and max_lat <= max(lats) + slack_lat
    )


def parcel_cells(terrain: TerrainData, outline: GeoJsonGeometry) -> ParcelCells:
    """Grid cells whose centre lies inside the parcel outline.

    An outline that is not a polygon has no inside and gives no cells.
    """
    if terrain.crs.upper() != SUPPORTED_CRS:
        return ParcelCells(supported=False)
    polygon = shape(outline.model_dump())
    if polygon.is_empty or polygon.geom_type not in ("Polygon", "MultiPolygon"):
        return ParcelCells(supported=True)

    inside: list[tuple[int, int, float, float, float | None]] = []
    for row, values in enumerate(terrain.elevations_m):
        for col, elevation in enumerate(values):
            lon, lat = _centre(terrain.transform, row, col)
            if polygon.contains(Point(lon, lat)):
                inside.append((row, col, lon, lat, elevation))
    covers = _covers(terrain, polygon.bounds)
    kept = [item for item in inside if item[4] is not None]
    if not kept:
        return ParcelCells(supported=True, inside_count=len(inside), covers_outline=covers)

    lon0 = sum(item[2] for item in kept) / len(kept)
    lat0 = sum(item[3] for item in kept) / len(kept)
    east_m, north_m = metres_per_degree(lat0)
    a, b, _, d, e, _ = terrain.transform
    return ParcelCells(
        supported=True,
        cells=tuple(
            Cell(
                row=row,
                col=col,
                x_m=(lon - lon0) * east_m,
                y_m=(lat - lat0) * north_m,
                elevation_m=elevation,
            )
            for row, col, lon, lat, elevation in kept
        ),
        inside_count=len(inside),
        # Length on the ground of one step along a grid row and along a column.
        cell_size_m=(math.hypot(a * east_m, d * north_m), math.hypot(b * east_m, e * north_m)),
        covers_outline=covers,
    )
