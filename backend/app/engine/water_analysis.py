"""Where the waters around a parcel lie: distance, side and relation to the slope.

For each group the rules ask about (ditch, watercourse, water body) the
nearest object of the stored water data is found and described by:

- the distance from the parcel outline in metres (0 when it crosses the parcel),
- the side of the parcel it lies on: the compass sector of the direction from
  the middle of the parcel to the middle of the near part of the object (what
  lies no farther from the outline than its nearest point plus a set span),
- whether that side is the one towards which the terrain falls; unknown when
  the terrain analysis gives no downhill direction.

An object that is not in the data does not exist here: a group without
objects has no nearest one, and nothing is assumed about it.

Distances are measured on a local flat grid in metres centred on the parcel
(the same ellipsoid radii as the terrain grid), accurate to well under a
metre over the few hundred metres concerned.

Pure: no network, clock or files.
"""

from dataclasses import dataclass

from shapely import transform
from shapely.errors import ShapelyError
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from app.contracts.causes import RetentionSite
from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import HydroData
from app.engine import water_params as params
from app.engine.terrain_analysis import COMPASS, TerrainAnalysis, azimuth_of, compass_index
from app.engine.terrain_grid import metres_per_degree


@dataclass(frozen=True)
class NearestWater:
    """The nearest object of one group."""

    kind: str
    name: str | None
    distance_m: float
    # Direction from the middle of the parcel, degrees clockwise from north;
    # None when the object passes through the middle itself.
    azimuth_deg: float | None
    # Adjective naming the side of the parcel, e.g. "północna".
    side: str | None
    # True when the object lies on the side towards which the terrain falls.
    downhill: bool | None
    # The near part of the object on the local grid; None when it is not a line
    # or an area.
    near_part_m: BaseGeometry | None

    @property
    def on_parcel(self) -> bool:
        return self.distance_m < params.ON_PARCEL_WITHIN_M

    @property
    def label(self) -> str:
        return params.KIND_LABELS[self.kind]

    @property
    def location(self) -> str:
        """Where the object lies, as a phrase for the texts of the Report."""
        if self.on_parcel:
            return params.ON_PARCEL
        distance = round(self.distance_m)
        if self.side is None:
            return params.OFF_PARCEL_NO_SIDE.format(distance=distance)
        return params.OFF_PARCEL.format(distance=distance, side=self.side)


@dataclass(frozen=True)
class WaterAnalysis:
    """Result of the analysis; `nearest` has an entry per group with objects."""

    objects_count: int
    nearest: dict[str, NearestWater]
    # Water retention site derived from the nearest ditch; None without one.
    site: RetentionSite | None = None


class _LocalGrid:
    """Flat grid in metres centred on a point given in degrees."""

    def __init__(self, lon: float, lat: float) -> None:
        self._lon, self._lat = lon, lat
        self._per_lon, self._per_lat = metres_per_degree(lat)

    def _forward(self, lon, lat):
        return (lon - self._lon) * self._per_lon, (lat - self._lat) * self._per_lat

    def _back(self, east, north):
        return self._lon + east / self._per_lon, self._lat + north / self._per_lat

    def to_metres(self, geometry: BaseGeometry) -> BaseGeometry:
        return transform(geometry, self._forward, interleaved=False)

    def to_degrees(self, geometry: BaseGeometry) -> BaseGeometry:
        return transform(geometry, self._back, interleaved=False)


def angle_between(first_deg: float, second_deg: float) -> float:
    """Smaller angle between two azimuths, 0-180 degrees."""
    difference = abs(first_deg - second_deg) % 360.0
    return min(difference, 360.0 - difference)


def _describe(
    kind: str,
    name: str | None,
    shape_m: BaseGeometry,
    outline_m: BaseGeometry,
    downhill_azimuth_deg: float | None,
) -> NearestWater:
    distance = outline_m.distance(shape_m)
    near = shape_m.intersection(outline_m.buffer(distance + params.NEAR_PART_SPAN_M))
    middle = (shape_m if near.is_empty else near).centroid
    # The grid is centred on the middle of the parcel, so the coordinates of
    # the point are the vector from the middle of the parcel to it.
    azimuth = side = downhill = None
    if max(abs(middle.x), abs(middle.y)) >= params.ON_PARCEL_WITHIN_M:
        azimuth = azimuth_of(middle.x, middle.y)
        side = COMPASS[compass_index(azimuth)][1]
        if downhill_azimuth_deg is not None:
            apart = angle_between(azimuth, downhill_azimuth_deg)
            downhill = apart <= params.DOWNHILL_SIDE_HALF_ANGLE_DEG
    return NearestWater(
        kind=kind,
        name=name,
        distance_m=distance,
        azimuth_deg=azimuth,
        side=side,
        downhill=downhill,
        near_part_m=None if near.is_empty else near,
    )


def _rounded(value):
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return round(float(value), params.COORDINATE_DECIMALS)


def _site(found: NearestWater, grid: _LocalGrid) -> RetentionSite | None:
    """The near part of a ditch, as a candidate site for the map."""
    part = found.near_part_m
    if part is None or part.geom_type not in ("LineString", "MultiLineString"):
        return None
    geometry = mapping(grid.to_degrees(part))
    return RetentionSite(
        id=params.SITE_ID,
        label=params.SITE_LABEL.format(kind=params.KIND_LABELS_GENITIVE[found.kind]),
        geometry=GeoJsonGeometry(
            type=geometry["type"], coordinates=_rounded(geometry["coordinates"])
        ),
    )


def analyse_waters(
    hydro: HydroData, outline: GeoJsonGeometry, terrain: TerrainAnalysis | None = None
) -> WaterAnalysis:
    """Nearest ditch, watercourse and water body of the parcel.

    `terrain` gives the downhill direction; without it, or when the terrain
    shows none, the relation to the slope stays unknown.
    """
    parcel = shape(outline.model_dump())
    middle = parcel.centroid
    grid = _LocalGrid(middle.x, middle.y)
    outline_m = grid.to_metres(parcel)
    downhill = None if terrain is None else terrain.downhill_azimuth_deg
    group_of = {kind: group for group, kinds in params.GROUPS.items() for kind in kinds}
    nearest: dict[str, NearestWater] = {}
    for item in hydro.objects:
        group = group_of.get(item.kind)
        if group is None:
            continue
        try:
            shape_m = grid.to_metres(shape(item.geometry.model_dump()))
            if shape_m.is_empty:
                continue
            distance = outline_m.distance(shape_m)
        except (ShapelyError, ValueError, TypeError, IndexError):
            continue
        if group in nearest and nearest[group].distance_m <= distance:
            continue
        nearest[group] = _describe(item.kind, item.name, shape_m, outline_m, downhill)
    ordered = {group: nearest[group] for group in params.GROUPS if group in nearest}
    ditch = ordered.get("ditch")
    return WaterAnalysis(
        objects_count=len(hydro.objects),
        nearest=ordered,
        site=None if ditch is None else _site(ditch, grid),
    )
