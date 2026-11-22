"""Helpers for the satellite tests: a recorded catalogue answer and tiny scene files."""

import asyncio
import json
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import shape

from app.contracts.common import GeoJsonGeometry
from app.sources.raster import WGS84, reproject_geometry

FIXTURES = Path(__file__).parent / "fixtures" / "earth_search"

# Outline of the parcel the catalogue answer was recorded for (about 2.5 ha).
OUTLINE = GeoJsonGeometry(
    type="Polygon",
    coordinates=[
        [
            [18.2024467151364, 52.749196783764],
            [18.2003168413755, 52.7502632828683],
            [18.1991119805698, 52.7494166763537],
            [18.201060596431, 52.7484852200819],
            [18.2016203684626, 52.7482176279139],
            [18.2024467151364, 52.749196783764],
        ]
    ],
)



def _box(lon: float, lat: float, width_deg: float, height_deg: float) -> GeoJsonGeometry:
    east, north = lon + width_deg, lat + height_deg
    return GeoJsonGeometry(
        type="Polygon",
        coordinates=[[[lon, lat], [east, lat], [east, north], [lon, north], [lon, lat]]],
    )


# A strip about 200 m long and 25 m wide inside the parcel area: enough 10 m
# pixels for NDVI, too few 20 m pixels for NDMI.
NARROW = _box(18.1996, 52.7492, 0.00297, 0.000225)
# About 7 m by 11 m: too small for either grid.
TINY = _box(18.2008, 52.7493, 1e-4, 1e-4)

# The recorded answer (21.05-20.06.2023, twelve acquisition days) lists every
# day twice: one copy per overlapping tile.
TILE_CRS = {"34UCD": "EPSG:32634", "33UYU": "EPSG:32633"}
FIRST_TILE = "33UYU"  # both tiles are equally frequent, so the first by name is read

FINE_PIXELS, COARSE_PIXELS = 60, 30  # 600 m square on the 10 m and the 20 m grid


def recorded_answer() -> dict:
    return json.loads((FIXTURES / "search_2023_06.json").read_text(encoding="utf-8"))


def scene_id(day: str, tile: str = FIRST_TILE) -> str:
    """Scene id of the recorded answer for a day given as YYYYMMDD."""
    ids = [
        feature["id"]
        for feature in recorded_answer()["features"]
        if f"_{tile}_{day}_" in feature["id"]
    ]
    assert len(ids) == 1, ids
    return ids[0]


def hrefs_of(scene: str) -> dict[str, str]:
    feature = next(f for f in recorded_answer()["features"] if f["id"] == scene)
    return {name: asset["href"] for name, asset in feature["assets"].items()}


def grid_origin(crs: str, shift_m: float = 0.0) -> tuple[float, float]:
    """Upper-left corner of the test rasters: 100 m beyond the parcel, on a 20 m lattice."""
    min_x, _, _, max_y = reproject_geometry(shape(OUTLINE.model_dump()), WGS84, crs).bounds
    west = np.floor((min_x - 100) / 20) * 20 + shift_m
    north = np.ceil((max_y + 100) / 20) * 20 + shift_m
    return float(west), float(north)


def _write(path: Path, values, pixels: int, pixel_m: float, crs: str, origin, dtype: str):
    data = np.broadcast_to(np.asarray(values, dtype=dtype), (pixels, pixels))
    with rasterio.open(
        path, "w", driver="GTiff", height=pixels, width=pixels, count=1,
        dtype=dtype, crs=crs, transform=from_origin(*origin, pixel_m, pixel_m), nodata=0,
    ) as dataset:
        dataset.write(data, 1)
    return path


class SceneFiles:
    """Local files standing in for remote scene files, with a log of what was opened."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._paths: dict[str, Path] = {}
        self._lock = threading.Lock()
        self.opened: list[str] = []

    def add(
        self, scene: str, *, scl=4, red=1000, nir=3000, nir08=3000, swir=2000,
        crs: str | None = None, shift_m: float = 0.0,
    ) -> None:
        """Write the five files of a scene; values are constants or whole arrays."""
        self.add_hrefs(
            hrefs_of(scene), crs or TILE_CRS[scene.split("_")[1]],
            scl=scl, red=red, nir=nir, nir08=nir08, swir=swir, shift_m=shift_m, label=scene,
        )  # fmt: skip

    def add_hrefs(
        self, hrefs: dict[str, str], crs: str, *, scl=4, red=1000, nir=3000, nir08=3000,
        swir=2000, shift_m: float = 0.0, label: str = "scene",
    ) -> None:
        """Write the five files of a scene given its file addresses by layer name."""
        origin = grid_origin(crs, shift_m)
        layers = {
            "scl": (scl, COARSE_PIXELS, 20.0, "uint8"),
            "red": (red, FINE_PIXELS, 10.0, "uint16"),
            "nir": (nir, FINE_PIXELS, 10.0, "uint16"),
            "nir08": (nir08, COARSE_PIXELS, 20.0, "uint16"),
            "swir16": (swir, COARSE_PIXELS, 20.0, "uint16"),
        }
        for name, href in hrefs.items():
            values, pixels, pixel_m, dtype = layers[name]
            path = self._directory / f"{label}_{name}.tif"
            self._paths[href] = _write(path, values, pixels, pixel_m, crs, origin, dtype)

    @contextmanager
    def opener(self, href: str):
        with self._lock:
            self.opened.append(href)
        if href not in self._paths:
            raise AssertionError(f"unexpected file opened: {href}")
        with rasterio.open(self._paths[href]) as dataset:
            yield dataset

    def opened_layers(self, scene: str) -> set[str]:
        """Names of the layers of a scene that were opened."""
        return {name for name, href in hrefs_of(scene).items() if href in self.opened}


class Deadlines:
    """Stands in for waiting out a time limit: a wait ends when the test fires it.

    The n-th call of `sleep` returns after the n-th call of `fire`, whatever
    time has passed, so tests of the time limits do not depend on how fast
    the machine is. `hold` blocks a worker thread until the test is over.
    """

    def __init__(self) -> None:
        self.calls: list[float] = []
        self._fired = 0
        self._keys: set[str] = set()
        self._lock = threading.Lock()
        self._release = threading.Event()

    def fire(self, once: str | None = None) -> None:
        """End the next wait; calls sharing a `once` key count as one."""
        with self._lock:
            if once is None or once not in self._keys:
                self._fired += 1
            if once is not None:
                self._keys.add(once)

    async def sleep(self, seconds: float) -> None:
        with self._lock:
            index = len(self.calls)
            self.calls.append(seconds)
        waited = 0
        while self._fired <= index:
            await asyncio.sleep(0.002)
            waited += 1
            assert waited < 10_000, "the time limit was waited for, but the test never fired it"

    def hold(self) -> None:
        self._release.wait(timeout=30)

    def close(self) -> None:
        self._release.set()


# Acquisition days of the recorded answer, newest first (YYYYMMDD).
DAYS = (
    "20230619", "20230616", "20230614", "20230611", "20230609", "20230606",
    "20230604", "20230601", "20230530", "20230527", "20230525", "20230522",
)  # fmt: skip


def in_year(payload: dict, year: int) -> dict:
    """The recorded answer as if its scenes had been taken in another year."""
    text = json.dumps(payload).replace('"datetime": "2023-', f'"datetime": "{year}-')
    return json.loads(text)


def catalogue(
    payload: dict | None = None, seen: list | None = None, years: tuple[int, ...] = ()
) -> httpx.MockTransport:
    """Transport answering every search with the same recorded page.

    A search for a year in `years` gets the recorded scenes moved to that
    year (the same files under the same addresses).
    """
    answer = recorded_answer() if payload is None else payload

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        asked = json.loads(request.content)["datetime"]
        year = next((year for year in years if f"/{year}-" in asked), None)
        return httpx.Response(200, json=answer if year is None else in_year(answer, year))

    return httpx.MockTransport(handler)
