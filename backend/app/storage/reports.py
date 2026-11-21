"""Report store: analyses, their source data and their Reports in one SQLite file.

The store has no clock: callers pass the current time. Every call opens its
own connection, so the object can be used from any thread; callers running on
the event loop wrap the calls in `asyncio.to_thread`. A stored Report is never
rewritten, and rows older than the retention time are invisible to readers
even before they are physically deleted.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from app.contracts.analyses import AnalysisRequest, CropHistory, SourceProgress
from app.contracts.report import Limitation, Report
from app.contracts.source_data import SourceData
from app.storage import params
from app.storage.schema import SCHEMA, UNFINISHED_STATES

StoredState = Literal["running", "finalizing", "done", "failed"]

_PROGRESS = TypeAdapter(list[SourceProgress])
_LIMITATIONS = TypeAdapter(list[Limitation])
_UNFINISHED = ", ".join(f"'{state}'" for state in UNFINISHED_STATES)
_SUMMARY_COLUMNS = (
    "report_id, state, parcel_id, crop_id, analysis_date, created_ts, finished_ts, "
    "error_code, error_message, sources_json, crop_history_json"
)


class AnalysisNotOpenError(Exception):
    """The analysis is unknown or no longer in the state the write needs."""


@dataclass(frozen=True)
class AnalysisRecord:
    """An analysis without its large payloads."""

    report_id: str
    state: StoredState
    parcel_id: str
    crop_id: str
    analysis_date: date
    created_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    sources: list[SourceProgress]
    crop_history: CropHistory | None

    @property
    def finished(self) -> bool:
        return self.state in ("done", "failed")


@dataclass(frozen=True)
class StoredInputs:
    """Everything a finished analysis was computed from; enough to compute it again."""

    record: AnalysisRecord
    source_data: SourceData
    source_limitations: list[Limitation]


def _history(text: str | None) -> CropHistory | None:
    return None if text is None else CropHistory.model_validate_json(text)


def _record(row: sqlite3.Row) -> AnalysisRecord:
    finished = row["finished_ts"]
    return AnalysisRecord(
        report_id=row["report_id"],
        state=row["state"],
        parcel_id=row["parcel_id"],
        crop_id=row["crop_id"],
        analysis_date=date.fromisoformat(row["analysis_date"]),
        created_at=datetime.fromtimestamp(row["created_ts"], UTC),
        finished_at=None if finished is None else datetime.fromtimestamp(finished, UTC),
        error_code=row["error_code"],
        error_message=row["error_message"],
        sources=_PROGRESS.validate_json(row["sources_json"]),
        crop_history=_history(row["crop_history_json"]),
    )


class ReportStore:
    def __init__(self, path: str | Path, retention: timedelta = params.REPORT_RETENTION) -> None:
        self._path = Path(path)
        self._retention = retention
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=params.BUSY_TIMEOUT_S)
        connection.row_factory = sqlite3.Row
        return connection

    def _oldest_kept(self, now: datetime) -> float:
        return (now - self._retention).timestamp()

    def _write(self, sql: str, values: tuple) -> list[sqlite3.Row]:
        """Run one changing statement in its own transaction; rows of RETURNING."""
        with closing(self._connect()) as connection, connection:
            return connection.execute(sql, values).fetchall()

    def _read(self, columns: str, report_id: str, now: datetime) -> sqlite3.Row | None:
        with closing(self._connect()) as connection:
            return connection.execute(
                f"SELECT {columns} FROM analyses WHERE report_id = ? AND created_ts >= ?",
                (report_id, self._oldest_kept(now)),
            ).fetchone()

    def create(
        self,
        report_id: str,
        request: AnalysisRequest,
        sources: list[SourceProgress],
        created_at: datetime,
    ) -> None:
        """Register a started analysis."""
        self._write(
            "INSERT INTO analyses (report_id, state, parcel_id, crop_id, analysis_date, "
            "created_ts, sources_json) VALUES (?, 'running', ?, ?, ?, ?, ?)",
            (
                report_id,
                request.parcel_id,
                request.crop_id,
                request.analysis_date.isoformat(),
                created_at.timestamp(),
                _PROGRESS.dump_json(sources).decode(),
            ),
        )

    def get(self, report_id: str, now: datetime) -> AnalysisRecord | None:
        row = self._read(_SUMMARY_COLUMNS, report_id, now)
        return None if row is None else _record(row)

    def report_json(self, report_id: str, now: datetime) -> str | None:
        """The Report exactly as it was written; None when there is none."""
        row = self._read("report_json", report_id, now)
        return None if row is None else row["report_json"]

    def inputs(self, report_id: str, now: datetime) -> StoredInputs | None:
        """Stored source data of a finished analysis, for results derived from it."""
        row = self._read(
            f"{_SUMMARY_COLUMNS}, source_data_json, source_limitations_json", report_id, now
        )
        if row is None or row["source_data_json"] is None:
            return None
        return StoredInputs(
            record=_record(row),
            source_data=SourceData.model_validate_json(row["source_data_json"]),
            source_limitations=_LIMITATIONS.validate_json(row["source_limitations_json"]),
        )

    def set_crop_history(self, report_id: str, history: CropHistory) -> bool:
        """Attach the crop history; False when the analysis no longer accepts it."""
        changed = self._write(
            "UPDATE analyses SET crop_history_json = ? "
            "WHERE report_id = ? AND state = 'running' RETURNING report_id",
            (history.model_dump_json(), report_id),
        )
        return bool(changed)

    def begin_finalize(self, report_id: str) -> CropHistory | None:
        """Stop accepting the crop history and return the one given so far."""
        rows = self._write(
            "UPDATE analyses SET state = 'finalizing' "
            "WHERE report_id = ? AND state = 'running' RETURNING crop_history_json",
            (report_id,),
        )
        if not rows:
            raise AnalysisNotOpenError(report_id)
        return _history(rows[0]["crop_history_json"])

    def save_report(
        self,
        report: Report,
        source_data: SourceData,
        source_limitations: list[Limitation],
        sources: list[SourceProgress],
        finished_at: datetime,
    ) -> None:
        """Write the Report and everything it was computed from, once."""
        rows = self._write(
            "UPDATE analyses SET state = 'done', finished_ts = ?, sources_json = ?, "
            "source_data_json = ?, source_limitations_json = ?, report_json = ? "
            "WHERE report_id = ? AND state = 'finalizing' RETURNING report_id",
            (
                finished_at.timestamp(),
                _PROGRESS.dump_json(sources).decode(),
                source_data.model_dump_json(),
                _LIMITATIONS.dump_json(source_limitations).decode(),
                report.model_dump_json(),
                report.meta.report_id,
            ),
        )
        if not rows:
            raise AnalysisNotOpenError(report.meta.report_id)

    def save_failure(
        self,
        report_id: str,
        code: str,
        message: str,
        sources: list[SourceProgress],
        finished_at: datetime,
    ) -> bool:
        """Close an unfinished analysis as failed; False when it was already closed."""
        rows = self._write(
            "UPDATE analyses SET state = 'failed', finished_ts = ?, error_code = ?, "
            f"error_message = ?, sources_json = ? WHERE report_id = ? "
            f"AND state IN ({_UNFINISHED}) RETURNING report_id",
            (
                finished_at.timestamp(),
                code,
                message,
                _PROGRESS.dump_json(sources).decode(),
                report_id,
            ),
        )
        return bool(rows)

    def fail_unfinished(self, code: str, message: str, finished_at: datetime) -> int:
        """Close every unfinished analysis as failed; used after a process restart."""
        rows = self._write(
            "UPDATE analyses SET state = 'failed', finished_ts = ?, error_code = ?, "
            f"error_message = ? WHERE state IN ({_UNFINISHED}) RETURNING report_id",
            (finished_at.timestamp(), code, message),
        )
        return len(rows)

    def purge_expired(self, now: datetime) -> int:
        """Delete analyses older than the retention time; returns how many."""
        rows = self._write(
            "DELETE FROM analyses WHERE created_ts < ? RETURNING report_id",
            (self._oldest_kept(now),),
        )
        return len(rows)
