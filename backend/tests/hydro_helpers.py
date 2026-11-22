"""Helpers for the water tests: small class files written for a test, served like the real ones.

The files have the columns and the layout of the real class files: flat
coordinates in metres (easting, northing), rows of several counties in small
row groups. The default objects lie around the recorded parcel (county 0407),
whose outline spans about 445958-446183 east and 542807-543036 north.
"""

import asyncio
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from shapely import wkb
from shapely.geometry import LineString, Polygon, box, mapping

from app.contracts.common import GeoJsonGeometry
from app.contracts.source_data import HydroData, HydroObject
from app.sources.hydro import HydroSource, LiveBdot, LocalBdot
from app.sources.hydro_params import BDOT_CLASSES

COUNTY = "0407"
MODIFIED = "Sat, 21 Nov 2026 04:46:00 GMT"
URL = "https://files.test/{name}.parquet"

# (county, name, type, geometry) per class. One ditch runs 10 m east of the
# recorded parcel, one lies far away; a stream passes 300 m to the north; a
# pond lies 150 m to the south-west; the canal file has no object nearby.
NEAR_DITCH = LineString([(446193, 542700), (446193, 543100)])
OBJECTS = {
    "OT_SWRM_L": [
        ("0401", None, None, LineString([(400000, 500000), (400100, 500000)])),
        (COUNTY, None, None, NEAR_DITCH),
        (COUNTY, None, None, LineString([(450000, 548000), (450200, 548100)])),
        ("0415", None, None, LineString([(470000, 560000), (470100, 560000)])),
    ],
    "OT_SWRS_L": [
        (COUNTY, "Struga Testowa", "strumień", LineString([(445000, 543336), (447500, 543336)])),
    ],
    "OT_SWKN_L": [
        ("0401", "Kanał Daleki", None, LineString([(400000, 500000), (400100, 500100)])),
    ],
    "OT_PTWP_A": [
        (COUNTY, None, "woda stojąca", box(445780, 542640, 445830, 542690)),
        (COUNTY, "Rzeka Szeroka", "woda płynąca", box(446500, 542800, 446520, 543000)),
    ],
}


def write_class_files(directory: Path, objects: dict | None = None) -> Path:
    """One file per class in the directory; rows in groups of two."""
    directory.mkdir(parents=True, exist_ok=True)
    chosen = OBJECTS if objects is None else objects
    for name, _ in BDOT_CLASSES:
        rows = chosen.get(name, [])
        columns = {
            "TERYT": pa.array([row[0] for row in rows], pa.string()),
            "LOKALNYID": pa.array([f"{name}-{index}" for index in range(len(rows))], pa.string()),
            "NAZWA": pa.array([row[1] for row in rows], pa.string()),
            "GEOM": pa.array([wkb.dumps(row[3]) for row in rows], pa.binary()),
        }
        if name in ("OT_SWRS_L", "OT_PTWP_A"):
            columns["RODZAJ"] = pa.array([row[2] for row in rows], pa.string())
        pq.write_table(pa.table(columns), directory / f"{name}.parquet", row_group_size=2)
    return directory


class ClassFileServer:
    """Serves the files of a directory to HEAD and range requests; can be broken or slow."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.failure: Exception | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        if self.status != 200:
            return httpx.Response(self.status, text="error")
        content = (self.directory / request.url.path.rsplit("/", 1)[-1]).read_bytes()
        headers = {"Content-Length": str(len(content)), "Last-Modified": MODIFIED}
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        first, last = request.headers["Range"].removeprefix("bytes=").split("-")
        piece = content[int(first) : int(last) + 1]
        return httpx.Response(206, content=piece)


def live_link(server: ClassFileServer) -> LiveBdot:
    return LiveBdot(transport=httpx.MockTransport(server), url=URL)


def recorded_hydro_source(directory: Path) -> HydroSource:
    """The live link on files written for the test; no local copy."""
    server = ClassFileServer(write_class_files(directory / "water_remote"))
    return HydroSource(links=[live_link(server)])


def local_link(directory: Path, objects: dict | None = None) -> LocalBdot:
    return LocalBdot(write_class_files(directory, objects))


class SlowLink:
    """A link that does not answer within its limit."""

    name = "Wolne źródło wód"
    timeout_s = 0.05

    async def read(self, request):
        await asyncio.sleep(5)


def geometry(shape: LineString | Polygon) -> GeoJsonGeometry:
    data = mapping(shape)
    return GeoJsonGeometry.model_validate(
        {"type": data["type"], "coordinates": data["coordinates"]}
    )


def hydro(*objects: tuple[str, str | None, LineString | Polygon]) -> HydroData:
    """Water data from (kind, name, geometry in degrees) entries."""
    return HydroData(
        objects=[
            HydroObject(kind=kind, name=name, geometry=geometry(shape))
            for kind, name, shape in objects
        ]
    )
