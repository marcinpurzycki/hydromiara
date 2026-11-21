"""Local files of the Combined Drought Indicator (CDI), European Drought Observatory.

One GeoTIFF per ten-day period (dekad), named
`cdinx_m_edo_YYYYMMDD_t_VVV_sNN.tif`: the date is the first day of the dekad,
`VVV` the indicator version, `s` is `z` for a final file and `p` for
a provisional one, `NN` a serial number (README.txt shipped with the files).
The grid is EPSG:4326 with cells of 1/24 degree.

Cell values (file tag `08_VALUES_LEGEND`): 0 no drought, 1 watch, 2 warning,
3 alert, 4 recovery to normal, 5 temporary soil moisture recovery,
6 temporary vegetation recovery, 7 no data inside the model domain,
8 outside the model domain (also the nodata value of the file).
"""

import re
from datetime import date
from pathlib import Path

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.windows import Window

FILE_PATTERN = re.compile(r"cdinx_m_edo_(\d{4})(\d{2})(\d{2})_t_(\d{3})_([pz])(\d{2})\.tif")
GRID_EPSG = 4326
# Classes that carry information; 7 and 8 mean "no data" (see module docstring).
VALID_CLASSES = frozenset(range(7))

# Polish names of the classes, for texts shown next to the indicator.
CDI_CLASS_LABELS = {
    0: "brak suszy",
    1: "obserwacja: niedobór opadów",
    2: "ostrzeżenie: niedobór wilgoci w glebie",
    3: "alarm: stres roślinności",
    4: "powrót do normy",
    5: "chwilowa poprawa wilgotności gleby",
    6: "chwilowa poprawa stanu roślinności",
}


class DroughtFileError(Exception):
    """A file cannot be used: unreadable or on an unexpected grid."""


class PointOutsideGridError(Exception):
    """The point lies outside the extent of the indicator grid."""


def dekad_start(day: date) -> date:
    """First day of the ten-day period containing `day` (1st, 11th or 21st)."""
    return day.replace(day=min((day.day - 1) // 10, 2) * 10 + 1)


def next_dekad(start: date) -> date:
    """First day of the dekad following the one that starts on `start`."""
    if start.day < 21:
        return start.replace(day=start.day + 10)
    if start.month == 12:
        return date(start.year + 1, 1, 1)
    return date(start.year, start.month + 1, 1)


def count_dekads(first: date, last: date) -> int:
    """Number of dekads from the one starting on `first` to the one starting on `last`."""
    count, current = 0, first
    while current <= last:
        count, current = count + 1, next_dekad(current)
    return count


def index_files(data_dir: Path) -> dict[date, Path]:
    """Best file for every dekad found in the directory, ordered by date.

    A final file wins over a provisional one, then the newer indicator version,
    then the higher serial number.
    """
    best: dict[date, tuple[tuple[bool, int, int], Path]] = {}
    if not data_dir.is_dir():
        return {}
    for path in data_dir.iterdir():
        match = FILE_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        year, month, day, version, status, serial = match.groups()
        try:
            start = date(int(year), int(month), int(day))
        except ValueError:
            continue
        if start != dekad_start(start):
            continue
        rank = (status == "z", int(version), int(serial))
        if start not in best or rank > best[start][0]:
            best[start] = (rank, path)
    return {start: best[start][1] for start in sorted(best)}


def read_class(path: Path, lon: float, lat: float) -> int | None:
    """CDI class of the grid cell containing the point; None when the cell has no data."""
    try:
        with rasterio.open(path) as dataset:
            if dataset.crs is None or dataset.crs.to_epsg() != GRID_EPSG:
                raise DroughtFileError(f"{path.name}: unexpected coordinate system")
            bounds = dataset.bounds
            if not (bounds.left <= lon < bounds.right and bounds.bottom < lat <= bounds.top):
                raise PointOutsideGridError(path.name)
            row, col = dataset.index(lon, lat)
            value = int(dataset.read(1, window=Window(col, row, 1, 1))[0, 0])
    except RasterioIOError as error:
        raise DroughtFileError(f"{path.name}: cannot be read") from error
    return value if value in VALID_CLASSES else None
