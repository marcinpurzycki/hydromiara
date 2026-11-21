"""Drought background: CDI classes for the parcel location, read from local files.

Returns the dekads from 1 January of the tenth year before the analysis date
up to the dekad that contains the analysis date, so that the current season and
the same periods of the previous years are both covered. Nothing later than
that dekad is ever returned.

Note for users of the series: the last dekad may end up to nine days after
the analysis date; each entry carries the first day of its dekad.
"""

import asyncio
import os
import time
from datetime import UTC, date, datetime
from pathlib import Path

from app.contracts.source_data import CdiDekad, DroughtBackground, SourceOutcome
from app.sources.drought_files import (
    DroughtFileError,
    PointOutsideGridError,
    count_dekads,
    dekad_start,
    index_files,
    read_class,
)

SOURCE_NAME = "European Drought Observatory (EDO), Combined Drought Indicator (CDI)"
SOURCE_LICENSE = "CC BY 4.0"
DATA_DIR_ENV = "EDO_DATA_PATH"
DEFAULT_DATA_DIR = "/data/edo"
# Length of the multi-year window: ten years directly before the analysis date.
WINDOW_YEARS = 10

_NO_FILES = "Brak plików wskaźnika CDI na serwerze."
_OUTSIDE_GRID = "Działka leży poza zasięgiem siatki wskaźnika CDI."
_NO_VALUES = "Wskaźnik CDI nie ma wartości dla tego miejsca."


def _pl(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _years_back(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _coverage_notes(
    available: list[date], used: list[date], analysis_date: date, unreadable: int
) -> list[str]:
    """Sentences about what the returned series does not cover."""
    notes = []
    if available[0] > dekad_start(_years_back(analysis_date, WINDOW_YEARS)):
        notes.append(
            f"Wskaźnik CDI jest dostępny od {_pl(available[0])}, "
            "więc nie obejmuje całych 10 lat przed datą analizy."
        )
    if used[-1] < dekad_start(analysis_date):
        notes.append(
            f"Najnowsza dostępna dekada wskaźnika CDI zaczyna się {_pl(used[-1])}; "
            "dla późniejszych dni danych nie ma."
        )
    missing = count_dekads(used[0], used[-1]) - len(used)
    if missing:
        notes.append(f"W serii wskaźnika CDI brakuje plików dla {missing} dekad.")
    if unreadable:
        notes.append(f"Nie udało się odczytać plików wskaźnika CDI dla {unreadable} dekad.")
    return notes


def read_series(
    data_dir: Path, lon: float, lat: float, analysis_date: date
) -> tuple[DroughtBackground | None, str | None]:
    """CDI dekads for the point up to the analysis date, with a note on gaps.

    Returns no data together with the reason when nothing can be said
    for this point and date.
    """
    files = index_files(data_dir)
    if not files:
        return None, _NO_FILES
    available = list(files)
    if analysis_date < available[0]:
        return None, (
            f"Wskaźnik CDI jest dostępny od {_pl(available[0])}; "
            f"data analizy {_pl(analysis_date)} jest wcześniejsza."
        )
    first_wanted = date(analysis_date.year - WINDOW_YEARS, 1, 1)
    used = [start for start in available if first_wanted <= start <= analysis_date]
    if not used:
        return None, (
            f"Najnowsza dostępna dekada wskaźnika CDI zaczyna się {_pl(available[-1])}; "
            f"dla daty analizy {_pl(analysis_date)} danych nie ma."
        )

    dekads, unreadable = [], 0
    for start in used:
        try:
            cdi_class = read_class(files[start], lon, lat)
        except PointOutsideGridError:
            return None, _OUTSIDE_GRID
        except DroughtFileError:
            cdi_class, unreadable = None, unreadable + 1
        dekads.append(CdiDekad(date=start, cdi_class=cdi_class))
    if unreadable == len(used):
        return None, "Nie udało się odczytać plików wskaźnika CDI."
    if all(dekad.cdi_class is None for dekad in dekads):
        return None, _NO_VALUES

    notes = _coverage_notes(available, used, analysis_date, unreadable)
    return DroughtBackground(dekads=dekads), " ".join(notes) or None


class DroughtBackgroundSource:
    """Adapter for the CDI files kept in a local directory."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir or os.environ.get(DATA_DIR_ENV) or DEFAULT_DATA_DIR)

    async def fetch(
        self, lon: float, lat: float, analysis_date: date
    ) -> tuple[DroughtBackground | None, SourceOutcome]:
        """Series for an analysis together with the record of how it was obtained."""
        started = time.monotonic()
        try:
            data, message = await asyncio.to_thread(
                read_series, self.data_dir, lon, lat, analysis_date
            )
        except OSError:
            data, message = None, _NO_FILES
        data_date = None
        if data is not None:
            first, last = data.dekads[0].date, data.dekads[-1].date
            data_date = f"{first.isoformat()}/{last.isoformat()}"
        outcome = SourceOutcome(
            topic="drought_background",
            source_name=SOURCE_NAME if data else None,
            chain_step=1 if data else None,
            ok=data is not None,
            duration_s=round(time.monotonic() - started, 3),
            data_date=data_date,
            fetched_at=datetime.now(UTC),
            message=message,
        )
        return data, outcome


def get_drought_background_source() -> DroughtBackgroundSource:
    """Source reading the directory configured for this deployment."""
    return DroughtBackgroundSource()
