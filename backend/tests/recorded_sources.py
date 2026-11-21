"""Optional sources of an analysis for tests: recorded answers and small local rasters.

`recorded_optional_sources` builds the real adapters on recorded catalogue and
service answers; raster files are written into the given directory. `Broken`
and `Slow` stand in for an adapter of any category that raises or never ends.
"""

import asyncio
import json
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.orchestrator.sources import OptionalSources
from app.sources.drought_background import DroughtBackgroundSource
from app.sources.satellite import SatelliteSource
from app.sources.satellite_providers import EARTH_SEARCH
from app.sources.soil import SoilSource
from app.sources.terrain import TerrainSource
from app.sources.terrain_copernicus import CopernicusDem30
from tests.satellite_helpers import SceneFiles, catalogue, scene_id

FIXTURES = Path(__file__).parent / "fixtures"
EDO_DIR = FIXTURES / "edo"

# Days of the recorded catalogue answer that get scene files (June 2023).
SCENE_DAYS = ("20230619", "20230616", "20230614")
# A piece of an elevation tile around the recorded parcel, on the grid of the
# product north of 50 degrees: 1.5 arc seconds in longitude, 1 in latitude.
TILE_WEST, TILE_NORTH = 18.19, 52.76
TILE_DX, TILE_DY = 1.5 / 3600, 1.0 / 3600
TILE_COLS, TILE_ROWS = 60, 80


class Broken:
    """Adapter of any category whose fetch raises."""

    async def fetch(self, *args, **kwargs):
        raise RuntimeError("boom")


class Slow:
    """Adapter of any category whose fetch does not end in the time of a test."""

    async def fetch(self, *args, **kwargs):
        await asyncio.sleep(60)


def json_fixture(*parts: str) -> dict:
    return json.loads(FIXTURES.joinpath(*parts).read_text(encoding="utf-8"))


def answering(payload: dict, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=payload))


def recorded_soil_source(payload: dict | None = None, status: int = 200) -> SoilSource:
    answer = json_fixture("soilgrids", "profile_field.json") if payload is None else payload
    return SoilSource(transport=answering(answer, status))


def soil_payload_without_water(depth_label: str = "60-100cm") -> dict:
    """The recorded profile with both water contents of one layer set to null."""
    payload = json_fixture("soilgrids", "profile_field.json")
    for entry in payload["properties"]["layers"]:
        if entry["name"] in ("wv0033", "wv1500"):
            for depth in entry["depths"]:
                if depth["label"] == depth_label:
                    depth["values"]["mean"] = None
    return payload


def recorded_terrain_source(directory: Path, status: int = 200) -> TerrainSource:
    """The 30 m link on the recorded catalogue answer and a generated tile."""
    row, col = np.mgrid[0:TILE_ROWS, 0:TILE_COLS]
    path = directory / "elevation_tile.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=TILE_ROWS, width=TILE_COLS, count=1,
        dtype="float32", crs="EPSG:4326", nodata=-32767.0,
        transform=from_origin(TILE_WEST, TILE_NORTH, TILE_DX, TILE_DY),
    ) as tile:  # fmt: skip
        tile.write((100.0 - 0.5 * row - 0.25 * col).astype("float32"), 1)
    transport = answering(json_fixture("earth_search", "cop_dem_search_one.json"), status)
    link = CopernicusDem30(transport=transport, open_dataset=lambda href: rasterio.open(path))
    return TerrainSource(links=[link])


def recorded_satellite_source(directory: Path) -> SatelliteSource:
    """One service on the recorded catalogue answer, with clear scenes in June 2023."""
    files = SceneFiles(directory)
    for day in SCENE_DAYS:
        files.add(scene_id(day))
    return SatelliteSource(transport=catalogue(), opener=files.opener, providers=[EARTH_SEARCH])


def recorded_optional_sources(directory: Path) -> OptionalSources:
    return OptionalSources(
        soil=recorded_soil_source(),
        terrain=recorded_terrain_source(directory),
        satellite=recorded_satellite_source(directory),
        drought_background=DroughtBackgroundSource(EDO_DIR),
    )
