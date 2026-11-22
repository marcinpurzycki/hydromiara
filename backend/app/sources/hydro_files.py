"""Reading the water objects of one county from a BDOT10k GeoParquet file.

A file holds one object class for the whole country, with rows grouped by
county in row groups. Only the row groups of the wanted county are read: the
group statistics of the county column give the candidates, reading that column
alone confirms them, and the geometry and attributes are read from the
confirmed groups only. The same reading works on a local file and on a remote
one opened through HTTP range requests.

Blocking: meant to run in a worker thread. A remote file stops reading when
the deadline of the whole read has passed, so the thread ends soon after the
caller has given up.
"""

import io
import threading
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import pyarrow.parquet as pq

from app.sources import hydro_params as params


class ReadTooSlow(Exception):
    """The deadline of the whole read passed before it was complete."""


@dataclass(frozen=True)
class WaterRow:
    """One object of a class file, as stored there."""

    wkb: bytes
    name: str | None
    type_name: str | None


class RangeFile(io.RawIOBase):
    """Read-only remote file: every read is one HTTP range request.

    `lock` is shared by all files of one adapter, so that the server never
    gets two requests at a time: it drops connections made in parallel.
    """

    def __init__(
        self, client: httpx.Client, url: str, deadline: float, lock: threading.Lock
    ) -> None:
        super().__init__()
        self._client, self._url, self._deadline, self._lock = client, url, deadline, lock
        self._position = 0
        self.requests = 0
        self.bytes_read = 0
        head = self._send("HEAD", {})
        self.size = int(head.headers["Content-Length"])
        self.modified = _http_day(head.headers.get("Last-Modified"))

    def _send(self, method: str, headers: dict[str, str]) -> httpx.Response:
        left = self._deadline - time.monotonic()
        if left <= 0 or not self._lock.acquire(timeout=left):
            raise ReadTooSlow
        try:
            if time.monotonic() >= self._deadline:
                raise ReadTooSlow
            response = self._client.request(method, self._url, headers=headers)
        finally:
            self._lock.release()
        response.raise_for_status()
        self.requests += 1
        return response

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._position = offset
        elif whence == io.SEEK_CUR:
            self._position += offset
        else:
            self._position = self.size + offset
        return self._position

    def read(self, size: int = -1) -> bytes:
        left = self.size - self._position
        size = left if size < 0 else min(size, left)
        if size <= 0:
            return b""
        last = self._position + size - 1
        data = self._send("GET", {"Range": f"bytes={self._position}-{last}"}).content
        self._position += len(data)
        self.bytes_read += len(data)
        return data


def _http_day(value: str | None) -> str | None:
    """Day of an HTTP date header as YYYY-MM-DD; None when absent or unreadable."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    text = value.strip() if isinstance(value, str) else ""
    return text or None


def county_groups(parquet: pq.ParquetFile, county: str) -> list[int]:
    """Row groups whose county column really holds the county."""
    metadata = parquet.metadata
    column = parquet.schema_arrow.names.index(params.COUNTY_COLUMN)
    groups = []
    for index in range(metadata.num_row_groups):
        statistics = metadata.row_group(index).column(column).statistics
        if statistics is not None and statistics.has_min_max:
            if not statistics.min <= county <= statistics.max:
                continue
        codes = parquet.read_row_group(index, columns=[params.COUNTY_COLUMN], use_threads=False)
        if county in codes.column(params.COUNTY_COLUMN).to_pylist():
            groups.append(index)
    return groups


def read_county(source: Any, county: str) -> list[WaterRow]:
    """All objects of the county from one class file (a path or a file object)."""
    parquet = pq.ParquetFile(source)
    names = parquet.schema_arrow.names
    optional = [name for name in (params.NAME_COLUMN, params.TYPE_COLUMN) if name in names]
    wanted = [params.COUNTY_COLUMN, params.GEOMETRY_COLUMN, *optional]
    rows: list[WaterRow] = []
    for index in county_groups(parquet, county):
        table = parquet.read_row_group(index, columns=wanted, use_threads=False)
        for row in table.to_pylist():
            wkb = row[params.GEOMETRY_COLUMN]
            if row[params.COUNTY_COLUMN] != county or not wkb:
                continue
            rows.append(
                WaterRow(
                    wkb=bytes(wkb),
                    name=_text(row.get(params.NAME_COLUMN)),
                    type_name=_text(row.get(params.TYPE_COLUMN)),
                )
            )
    return rows
