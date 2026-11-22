"""Points of a parcel at which the soil category map is read. Pure.

One answer of the map service is one cell, and parcels are often mixed, so
the parcel is sampled on a regular lattice: centres of the cells of an n x n
division of the bounding box that fall inside the outline. The densest
lattice that keeps the number of points within the limit is used.
"""

import numpy as np
import shapely
from shapely import Point as ShapelyPoint
from shapely.geometry.base import BaseGeometry

from app.sources import soil_params as params

Point = tuple[float, float]  # longitude, latitude


def _lattice(outline: BaseGeometry, side: int) -> list[Point]:
    west, south, east, north = outline.bounds
    xs = west + (np.arange(side) + 0.5) * (east - west) / side
    ys = south + (np.arange(side) + 0.5) * (north - south) / side
    grid_x, grid_y = np.meshgrid(xs, ys)
    candidates = [(float(x), float(y)) for x, y in zip(grid_x.ravel(), grid_y.ravel())]
    inside = shapely.contains(outline, np.array([ShapelyPoint(x, y) for x, y in candidates]))
    return [point for point, is_inside in zip(candidates, inside) if is_inside]


def sample_points(outline: BaseGeometry, limit: int = params.MAX_SAMPLE_POINTS) -> list[Point]:
    """Up to `limit` points inside the outline (EPSG:4326), row by row from the south.

    A parcel too narrow for any lattice point gets one point guaranteed to
    lie inside it.
    """
    best: list[Point] = []
    for side in range(1, params.MAX_LATTICE_SIDE + 1):
        points = _lattice(outline, side)
        if len(points) > limit:
            break
        if len(points) > len(best):
            best = points
    if best:
        return best
    inner = outline.representative_point()
    return [(float(inner.x), float(inner.y))]
