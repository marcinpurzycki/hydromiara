"""Helpers for the satellite tests: a recorded catalogue answer and tiny scene files."""

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

# The recorded answer lists every day twice: one copy per overlapping tile.
TILE_CRS = {"34UCD": "EPSG:32634", "33UYU": "EPSG:32633"}
FIRST_TILE = "34UCD"  # the copy the adapter tries first (scene id, descending)

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
        self, scene: str, *, scl=4, red=1000, nir=3000, swir=2000,
        crs: str | None = None, shift_m: float = 0.0,
    ) -> None:
        """Write the four files of a scene; values are constants or whole arrays."""
        self.add_hrefs(
            hrefs_of(scene), crs or TILE_CRS[scene.split("_")[1]],
            scl=scl, red=red, nir=nir, swir=swir, shift_m=shift_m, label=scene,
        )  # fmt: skip

    def add_hrefs(
        self, hrefs: dict[str, str], crs: str, *, scl=4, red=1000, nir=3000, swir=2000,
        shift_m: float = 0.0, label: str = "scene",
    ) -> None:
        """Write the four files of a scene given its file addresses by layer name."""
        origin = grid_origin(crs, shift_m)
        layers = {
            "scl": (scl, COARSE_PIXELS, 20.0, "uint8"),
            "red": (red, FINE_PIXELS, 10.0, "uint16"),
            "nir": (nir, FINE_PIXELS, 10.0, "uint16"),
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


def catalogue(payload: dict | None = None, seen: list | None = None) -> httpx.MockTransport:
    """Transport answering every search with the same recorded page."""
    answer = recorded_answer() if payload is None else payload

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=answer)

    return httpx.MockTransport(handler)
