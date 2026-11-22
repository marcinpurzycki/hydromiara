"""Report store: analyses, their source data and their Reports in one SQLite file.

The store has no clock: callers pass the current time. Every call opens its
own connection, so the object can be used from any thread; callers running on
the event loop wrap the calls in `asyncio.to_thread`. A stored Report is never
rewritten, and rows older than the retention time are invisible to readers
even before they are physically deleted.
"""

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from app.contracts.analyses import AnalysisRequest, CropHistory, SourceProgress
from app.contracts.report import Limitation, Report
from app.contracts.source_data import SourceData
from app.storage import params
from app.storage.records import (
    LIMITATIONS,
    PROGRESS,
    SUMMARY_COLUMNS,
    UNFINISHED,
    AnalysisRecord,
    StoredInputs,
    StoredState,
    history_of,
    record_of,
)
from app.storage.schema import SCHEMA

__all__ = ["AnalysisNotOpenError", "AnalysisRecord", "ReportStore", "StoredInputs", "StoredState"]


class AnalysisNotOpenError(Exception):
    """The analysis is unknown or no longer in the state the write needs."""


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
        crop_history: CropHistory | None = None,
    ) -> None:
        """Register a started analysis; `crop_history` is the one it starts with."""
        self._write(
            "INSERT INTO analyses (report_id, state, parcel_id, crop_id, analysis_date, "
            "created_ts, sources_json, crop_history_json) VALUES (?, 'running', ?, ?, ?, ?, ?, ?)",
            (
                report_id,
                request.parcel_id,
                request.crop_id,
                request.analysis_date.isoformat(),
                created_at.timestamp(),
                PROGRESS.dump_json(sources).decode(),
                None if crop_history is None else crop_history.model_dump_json(),
            ),
        )

    def get(self, report_id: str, now: datetime) -> AnalysisRecord | None:
        row = self._read(SUMMARY_COLUMNS, report_id, now)
        return None if row is None else record_of(row)

    def report_json(self, report_id: str, now: datetime) -> str | None:
        """The Report exactly as it was written; None when there is none."""
        row = self._read("report_json", report_id, now)
        return None if row is None else row["report_json"]

    def inputs(self, report_id: str, now: datetime) -> StoredInputs | None:
        """Stored source data of a finished analysis, for results derived from it."""
        row = self._read(
            f"{SUMMARY_COLUMNS}, source_data_json, source_limitations_json", report_id, now
        )
        if row is None or row["source_data_json"] is None:
            return None
        return StoredInputs(
            record=record_of(row),
            source_data=SourceData.model_validate_json(row["source_data_json"]),
            source_limitations=LIMITATIONS.validate_json(row["source_limitations_json"]),
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
        return history_of(rows[0]["crop_history_json"])

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
                PROGRESS.dump_json(sources).decode(),
                source_data.model_dump_json(),
                LIMITATIONS.dump_json(source_limitations).decode(),
                report.model_dump_json(),
                report.meta.report_id,
            ),
        )
        if not rows:
            raise AnalysisNotOpenError(report.meta.report_id)

    def save_derived(
        self, report: Report, source_id: str, history: CropHistory, created_at: datetime
    ) -> bool:
        """Write a Report computed from the stored data of the Report `source_id`.

        The new row is a finished analysis of its own: it gets a copy of the
        source data, so it stays complete when the source Report is deleted and
        can itself be derived from. False when the source is no longer there.
        """
        rows = self._write(
            "INSERT INTO analyses (report_id, state, parcel_id, crop_id, analysis_date, "
            "created_ts, finished_ts, sources_json, crop_history_json, source_data_json, "
            "source_limitations_json, report_json) "
            "SELECT ?, 'done', parcel_id, crop_id, analysis_date, ?, ?, sources_json, ?, "
            "source_data_json, source_limitations_json, ? FROM analyses "
            "WHERE report_id = ? AND state = 'done' AND created_ts >= ? RETURNING report_id",
            (
                report.meta.report_id,
                created_at.timestamp(),
                created_at.timestamp(),
                history.model_dump_json(),
                report.model_dump_json(),
                source_id,
                self._oldest_kept(created_at),
            ),
        )
        return bool(rows)

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
            f"AND state IN ({UNFINISHED}) RETURNING report_id",
            (
                finished_at.timestamp(),
                code,
                message,
                PROGRESS.dump_json(sources).decode(),
                report_id,
            ),
        )
        return bool(rows)

    def fail_unfinished(self, code: str, message: str, finished_at: datetime) -> int:
        """Close every unfinished analysis as failed; used after a process restart."""
        rows = self._write(
            "UPDATE analyses SET state = 'failed', finished_ts = ?, error_code = ?, "
            f"error_message = ? WHERE state IN ({UNFINISHED}) RETURNING report_id",
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
