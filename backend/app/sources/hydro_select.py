"""Choosing the water objects around a parcel from the rows of the class files.

The files hold flat coordinates in metres (EPSG:2180, easting first), so the
parcel outline is brought into that system and distances are measured there.
An object is kept when it lies within the radius of the outline. Its geometry
is cut to that neighbourhood, because a river section or a lake can reach far
beyond it, and stored in EPSG:4326 like every geometry of the Report.

Pure: no network, clock or files.
"""

from collections.abc import Iterable, Sequence

from shapely import wkb
from shapely.errors import ShapelyError
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import HydroObject
from app.sources import hydro_params as params
from app.sources.hydro_files import WaterRow
from app.sources.raster import reproject_geometry

_LINES = ("LineString", "MultiLineString")
_AREAS = ("Polygon", "MultiPolygon")


def county_of(parcel_id: str) -> str | None:
    """County code of a parcel identifier; None when it does not start with one."""
    code = parcel_id[: params.COUNTY_CODE_LENGTH]
    return code if len(code) == params.COUNTY_CODE_LENGTH and code.isdigit() else None


def outline_in_file_crs(outline: BaseGeometry) -> BaseGeometry:
    """The parcel outline (EPSG:4326) in the system of the class files."""
    return reproject_geometry(outline, params.REPORT_CRS, params.BDOT_CRS)


def kind_of(class_kind: str, type_name: str | None) -> str:
    """Kind of an object: its class, except for areas of flowing water."""
    flowing = (type_name or "").lower().startswith(params.FLOWING_WATER_PREFIX)
    if class_kind == params.WATER_BODY and flowing:
        return params.WATERCOURSE
    return class_kind


def _parts(geometry: BaseGeometry, wanted: Sequence[str]) -> BaseGeometry | None:
    """The geometry when it is of a wanted type; from a collection its wanted parts."""
    if geometry.is_empty:
        return None
    if geometry.geom_type in wanted:
        return geometry
    if geometry.geom_type != "GeometryCollection":
        return None
    kept = [part for part in geometry.geoms if part.geom_type in wanted and not part.is_empty]
    if not kept:
        return None
    # Parts of one object never overlap, so the union only gathers them.
    merged = kept[0]
    for part in kept[1:]:
        merged = merged.union(part)
    return merged if merged.geom_type in wanted else None


def _rounded(value):
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return round(float(value), params.COORDINATE_DECIMALS)


def to_report_geometry(geometry: BaseGeometry) -> GeoJsonGeometry:
    """Geometry of the class files as GeoJSON in EPSG:4326."""
    geographic = reproject_geometry(geometry, params.BDOT_CRS, params.REPORT_CRS)
    shape = mapping(geographic)
    return GeoJsonGeometry(type=shape["type"], coordinates=_rounded(shape["coordinates"]))


def select_objects(
    rows: Iterable[tuple[str, WaterRow]],
    outline: BaseGeometry,
    radius_m: float = params.RADIUS_M,
    max_objects: int = params.MAX_OBJECTS,
) -> list[HydroObject]:
    """Objects within the radius of the outline, nearest first.

    `rows` pairs the kind of the class with a row of its file; `outline` is in
    the system of the files. A row whose geometry cannot be read is left out.
    """
    neighbourhood = outline.buffer(radius_m)
    found: list[tuple[float, int, HydroObject]] = []
    for order, (class_kind, row) in enumerate(rows):
        try:
            geometry = wkb.loads(row.wkb)
            distance = outline.distance(geometry)
            if distance > radius_m:
                continue
            wanted = _AREAS if geometry.geom_type in _AREAS else _LINES
            cut = _parts(geometry.intersection(neighbourhood), wanted)
        except (ShapelyError, ValueError, TypeError):
            continue
        if cut is None:
            continue
        item = HydroObject(
            kind=kind_of(class_kind, row.type_name),
            name=row.name,
            geometry=to_report_geometry(cut),
        )
        found.append((distance, order, item))
    found.sort(key=lambda entry: entry[:2])
    return [item for _, _, item in found[:max_objects]]
