"""Slope, downhill direction and lowest part of a parcel from its elevation grid.

Method: a plane z = gx * x + gy * y + c is fitted by least squares to the
centres of the grid cells that lie inside the parcel outline (x east, y north,
in metres, for a geographic grid and for a metric one alike). The slope is the length of the gradient (gx, gy), the downhill
direction is opposite to it. Cells outside the outline are never used, so the
result does not depend on the margin of the grid.

How far the result can be trusted is measured from the data themselves: the
scatter of the elevations around the plane gives the standard error of the
gradient. When the slope is smaller than a set multiple of that error, the
direction and the lowest part are not given (`direction_resolved` is False):
the surface is flat within what the grid can show. The error covers scatter
between neighbouring cells only; an offset shared by all cells, or a tree
line read as ground by a surface model, is not visible to it.

A plane needs cells spread in two directions. With too few cells inside the
outline, or with cells in one line, nothing is computed and the status says so.

Pure: no network, clock or files.
"""

import math
from dataclasses import dataclass
from typing import Literal

from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import TerrainData
from app.engine.cause_params import DEFAULT_CAUSE_PARAMS, CauseParams
from app.engine.terrain_grid import Cell, parcel_cells

TerrainStatus = Literal["ok", "too_few_cells", "unsupported_grid"]

# Eight compass sectors clockwise from north: name of the direction and the
# adjective naming a part of the parcel.
COMPASS: tuple[tuple[str, str], ...] = (
    ("północ", "północna"),
    ("północny wschód", "północno-wschodnia"),
    ("wschód", "wschodnia"),
    ("południowy wschód", "południowo-wschodnia"),
    ("południe", "południowa"),
    ("południowy zachód", "południowo-zachodnia"),
    ("zachód", "zachodnia"),
    ("północny zachód", "północno-zachodnia"),
)
CENTRAL_PART = "środkowa"


@dataclass(frozen=True)
class TerrainAnalysis:
    """Result of the terrain analysis of one parcel (unrounded values)."""

    status: TerrainStatus
    # Cell centres inside the outline, and those of them with an elevation.
    cells_inside: int = 0
    cells_used: int = 0
    # Cell width (east-west) and height (north-south) on the ground, metres.
    cell_size_m: tuple[float, float] | None = None
    # False when the outline reaches beyond the grid.
    covers_parcel: bool = False
    slope_pct: float | None = None
    # Standard error of the slope from the misfit of the plane.
    slope_error_pct: float | None = None
    # True when the slope is told apart from the scatter of the elevations.
    direction_resolved: bool = False
    # Downhill direction, degrees clockwise from north; None when not resolved.
    downhill_azimuth_deg: float | None = None
    downhill_label: str | None = None
    # Adjective naming the lowest part of the parcel; None when not resolved.
    lowest_part: str | None = None
    # Highest minus lowest elevation of the cells used, metres.
    relief_m: float | None = None

    @property
    def analysed(self) -> bool:
        return self.status == "ok"


def compass_index(azimuth_deg: float) -> int:
    """Index of the compass sector (0 = north, clockwise) of an azimuth."""
    return int(((azimuth_deg % 360.0) + 22.5) // 45.0) % 8


def azimuth_of(east: float, north: float) -> float:
    """Azimuth of a vector in degrees clockwise from north, within 0-360."""
    return math.degrees(math.atan2(east, north)) % 360.0


@dataclass(frozen=True)
class _Plane:
    gradient_east: float
    gradient_north: float
    # Standard error of the gradient length (upper bound), metres per metre.
    gradient_error: float
    # Root mean square spread of the cells across their narrower direction.
    cross_spread_m: float


def _fit_plane(cells: tuple[Cell, ...]) -> _Plane:
    """Least-squares plane through the cells; positions are already centred."""
    n = len(cells)
    mean_z = sum(cell.elevation_m for cell in cells) / n
    sxx = sum(cell.x_m * cell.x_m for cell in cells)
    syy = sum(cell.y_m * cell.y_m for cell in cells)
    sxy = sum(cell.x_m * cell.y_m for cell in cells)
    sxz = sum(cell.x_m * (cell.elevation_m - mean_z) for cell in cells)
    syz = sum(cell.y_m * (cell.elevation_m - mean_z) for cell in cells)
    det = sxx * syy - sxy * sxy
    trace = sxx + syy
    smaller_eigenvalue = (trace - math.sqrt(max(0.0, trace * trace - 4 * det))) / 2
    cross_spread = math.sqrt(max(0.0, smaller_eigenvalue) / n)
    if det <= 0:
        return _Plane(0.0, 0.0, math.inf, cross_spread)
    gx = (sxz * syy - syz * sxy) / det
    gy = (syz * sxx - sxz * sxy) / det
    misfit = sum(
        (cell.elevation_m - mean_z - gx * cell.x_m - gy * cell.y_m) ** 2 for cell in cells
    )
    variance = misfit / (n - 3) if n > 3 else math.inf
    # Variances of gx and gy added: never below the error along the gradient.
    return _Plane(gx, gy, math.sqrt(variance * trace / det), cross_spread)


def _lowest_part(cells: tuple[Cell, ...], cell_m: float, params: CauseParams) -> str:
    """Where the lowest cells lie relative to the middle of all cells used."""
    count = max(1, math.ceil(params.lowest_part_share * len(cells)))
    # Cells as low as the last one counted belong to the lowest part too.
    limit = sorted(cell.elevation_m for cell in cells)[count - 1]
    lowest = [cell for cell in cells if cell.elevation_m <= limit]
    east = sum(cell.x_m for cell in lowest) / len(lowest)
    north = sum(cell.y_m for cell in lowest) / len(lowest)
    if math.hypot(east, north) < params.lowest_part_central_within_cells * cell_m:
        return CENTRAL_PART
    return COMPASS[compass_index(azimuth_of(east, north))][1]


def analyse_terrain(
    terrain: TerrainData,
    outline: GeoJsonGeometry,
    params: CauseParams = DEFAULT_CAUSE_PARAMS,
) -> TerrainAnalysis:
    """Slope, downhill direction and lowest part of the parcel."""
    grid = parcel_cells(terrain, outline)
    if not grid.supported:
        return TerrainAnalysis(status="unsupported_grid")
    cells = grid.cells
    common = {
        "cells_inside": grid.inside_count,
        "cells_used": len(cells),
        "cell_size_m": grid.cell_size_m,
        "covers_parcel": grid.covers_outline,
    }
    if len(cells) < params.terrain_min_cells or grid.cell_size_m is None:
        return TerrainAnalysis(status="too_few_cells", **common)
    smaller_cell_m = min(grid.cell_size_m)
    plane = _fit_plane(cells)
    if plane.cross_spread_m < params.terrain_min_cross_spread_cells * smaller_cell_m:
        return TerrainAnalysis(status="too_few_cells", **common)

    slope = math.hypot(plane.gradient_east, plane.gradient_north)
    resolved = slope > 0 and slope >= params.slope_min_signal_to_error * plane.gradient_error
    azimuth = azimuth_of(-plane.gradient_east, -plane.gradient_north) if resolved else None
    elevations = [cell.elevation_m for cell in cells]
    return TerrainAnalysis(
        status="ok",
        **common,
        slope_pct=100.0 * slope,
        slope_error_pct=100.0 * plane.gradient_error,
        direction_resolved=resolved,
        downhill_azimuth_deg=azimuth,
        downhill_label=None if azimuth is None else COMPASS[compass_index(azimuth)][0],
        lowest_part=_lowest_part(cells, smaller_cell_m, params) if resolved else None,
        relief_m=max(elevations) - min(elevations),
    )
