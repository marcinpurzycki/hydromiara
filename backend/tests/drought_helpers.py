"""Helpers for the drought background tests: tiny indicator files written on the fly."""

from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from app.sources.drought_files import next_dekad

# Upper-left corner and cell size of the 3x3 test grid (same cell size as the real files).
WEST, NORTH, CELL = 18.125, 52.791666, 1 / 24
INSIDE = (18.2, 52.75)


def file_name(start: date, version: str = "410", status: str = "z", serial: str = "01") -> str:
    return f"cdinx_m_edo_{start:%Y%m%d}_t_{version}_{status}{serial}.tif"


def write_file(path: Path, value: int, crs: str = "EPSG:4326") -> Path:
    """Write a 3x3 single-band file filled with one class value."""
    transform = Affine(CELL, 0.0, WEST, 0.0, -CELL, NORTH)
    with rasterio.open(
        path, "w", driver="GTiff", height=3, width=3, count=1,
        dtype="uint8", crs=crs, transform=transform, nodata=8,
    ) as dataset:
        dataset.write(np.full((3, 3), value, dtype="uint8"), 1)
    return path


def write_series(directory: Path, first: date, last: date, value: int = 0) -> None:
    """One file per dekad from `first` to `last` (both first days of dekads)."""
    current = first
    while current <= last:
        write_file(directory / file_name(current), value)
        current = next_dekad(current)
