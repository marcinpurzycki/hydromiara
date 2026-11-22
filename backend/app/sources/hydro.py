"""Waters around a parcel: ditches, canals, watercourses and water bodies.

Substitute chain: the BDOT10k class files of GUGiK read live through HTTP
range requests, then a local copy of the same files, then no data. The local
link is part of the chain only when all its files are present in the data
directory; filling and refreshing that directory is done elsewhere.

Nothing about the parcel is sent out: the requests name only the public class
files and byte ranges in them. The ranges are those of the row groups of the
county the parcel lies in, so the county is the most a server can infer.

The live read sees the objects of the parcel's county only; an object just
across a county border is not found, and a limitation of the Report says so.
"""

import asyncio
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import NamedTuple

import httpx
import pyarrow
from shapely.errors import ShapelyError
from shapely.geometry.base import BaseGeometry

from app.contracts.report import Limitation
from app.contracts.source_data import HydroData, SourceOutcome
from app.sources import hydro_params as params
from app.sources.chain import ChainLink, ChainTexts, LinkFailed, LinkReading, no_data, run_chain
from app.sources.hydro_files import RangeFile, ReadTooSlow, WaterRow, read_county
from app.sources.hydro_select import county_of, outline_in_file_crs, select_objects
from app.sources.raster import OutlineInput, as_geometry

_TEXTS = ChainTexts(no_data=params.NO_DATA, stepped_down=params.STEPPED_DOWN)
_READ_ERRORS = (httpx.HTTPError, OSError, pyarrow.ArrowException, KeyError, ValueError)


@dataclass(frozen=True)
class WaterRequest:
    """What a link needs: the county and the outline in the system of the files."""

    county: str
    outline: BaseGeometry


class HydroFetch(NamedTuple):
    """Waters for one analysis, how they were obtained and what they cannot show."""

    data: HydroData | None
    outcome: SourceOutcome
    limitations: list[Limitation]


def _date_range(days: Sequence[str | None]) -> str | None:
    known = sorted({day for day in days if day})
    if not known:
        return None
    return known[0] if len(known) == 1 else f"{known[0]}/{known[-1]}"


class LiveBdot:
    """The class files of GUGiK, read through HTTP range requests.

    The four classes are read one after another on one connection at a time,
    also across analyses: the server drops connections opened in parallel.
    """

    name = params.BDOT_SOURCE_NAME
    timeout_s = params.LIVE_TIMEOUT_S

    def __init__(
        self, transport: httpx.BaseTransport | None = None, url: str = params.BDOT_URL
    ) -> None:
        self._url = url
        self._lock = threading.Lock()
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": params.USER_AGENT},
            timeout=httpx.Timeout(
                params.REQUEST_READ_TIMEOUT_S, connect=params.REQUEST_CONNECT_TIMEOUT_S
            ),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )
        # Requests and bytes of the last read, for measurements.
        self.last_requests = 0
        self.last_bytes = 0

    async def read(self, request: WaterRequest) -> LinkReading[HydroData]:
        deadline = time.monotonic() + self.timeout_s
        return await asyncio.to_thread(self._read, request, deadline)

    def _read(self, request: WaterRequest, deadline: float) -> LinkReading[HydroData]:
        rows: list[tuple[str, WaterRow]] = []
        days: list[str | None] = []
        requests = received = 0
        try:
            for class_name, kind in params.BDOT_CLASSES:
                remote = RangeFile(
                    self._client, self._url.format(name=class_name), deadline, self._lock
                )
                rows += [(kind, row) for row in read_county(remote, request.county)]
                days.append(remote.modified)
                requests, received = requests + remote.requests, received + remote.bytes_read
        except ReadTooSlow:
            raise LinkFailed(params.READ_TOO_SLOW) from None
        except _READ_ERRORS:
            raise LinkFailed(params.READ_FAILED) from None
        self.last_requests, self.last_bytes = requests, received
        data = HydroData(objects=select_objects(rows, request.outline))
        return LinkReading(data=data, data_date=_date_range(days))


class LocalBdot:
    """A local copy of the same class files, kept in a data directory."""

    name = params.BDOT_LOCAL_SOURCE_NAME
    timeout_s = params.LOCAL_TIMEOUT_S

    def __init__(self, directory: Path | str | None = None) -> None:
        chosen = directory or os.environ.get(params.LOCAL_DIR_ENV) or params.DEFAULT_LOCAL_DIR
        self.directory = Path(chosen)

    def _paths(self) -> list[tuple[Path, str]]:
        return [(self.directory / f"{name}.parquet", kind) for name, kind in params.BDOT_CLASSES]

    @property
    def available(self) -> bool:
        """True when the file of every class is present."""
        return all(path.is_file() for path, _ in self._paths())

    async def read(self, request: WaterRequest) -> LinkReading[HydroData]:
        return await asyncio.to_thread(self._read, request)

    def _read(self, request: WaterRequest) -> LinkReading[HydroData]:
        rows: list[tuple[str, WaterRow]] = []
        days: list[date] = []
        try:
            for path, kind in self._paths():
                days.append(date.fromtimestamp(path.stat().st_mtime))
                rows += [(kind, row) for row in read_county(path, request.county)]
        except _READ_ERRORS:
            raise LinkFailed(params.READ_FAILED) from None
        oldest = min(days)
        data = HydroData(objects=select_objects(rows, request.outline))
        note = params.LOCAL_COPY_NOTE.format(day=oldest.strftime("%d.%m.%Y"))
        return LinkReading(data=data, data_date=oldest.isoformat(), note=note)


class HydroSource:
    """Water objects around a parcel from the first link that has them."""

    def __init__(
        self, links: Sequence[ChainLink] | None = None, local: LocalBdot | None = None
    ) -> None:
        # Given links replace the whole chain; otherwise the live link comes
        # first and the local copy follows whenever its files are present.
        self._links = None if links is None else list(links)
        self._live = LiveBdot() if links is None else None
        self._local = local if local is not None else LocalBdot()

    def links(self) -> list[ChainLink]:
        """The chain for the next analysis, primary link first."""
        if self._links is not None:
            return list(self._links)
        return [self._live, *([self._local] if self._local.available else [])]

    @property
    def timeout_s(self) -> float:
        """Longest time the whole chain may take."""
        return params.LIVE_TIMEOUT_S + params.LOCAL_TIMEOUT_S

    async def fetch(self, parcel_id: str, geometry: OutlineInput) -> HydroFetch:
        """Objects within the radius of the parcel outline given in EPSG:4326."""
        started = time.monotonic()
        county = county_of(parcel_id)
        try:
            outline = outline_in_file_crs(as_geometry(geometry))
        except (TypeError, ValueError, KeyError, AttributeError, ShapelyError):
            outline = None
        if county is None or outline is None or outline.is_empty:
            return HydroFetch(None, no_data("hydro", params.WRONG_PARCEL, started), [])
        result = await run_chain(
            "hydro", self.links(), WaterRequest(county, outline), texts=_TEXTS
        )
        limitations = [
            Limitation(text=text, affects="recommendations", permanent=False)
            for text in (params.SCOPE_LIMITATIONS if result.data is not None else ())
        ]
        return HydroFetch(result.data, result.outcome, limitations)
