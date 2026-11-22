"""Rows of the report store as objects: an analysis and what it was computed from."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import TypeAdapter

from app.contracts.analyses import CropHistory, SourceProgress
from app.contracts.report import Limitation
from app.contracts.source_data import SourceData
from app.storage.schema import UNFINISHED_STATES

StoredState = Literal["running", "finalizing", "done", "failed"]

PROGRESS = TypeAdapter(list[SourceProgress])
LIMITATIONS = TypeAdapter(list[Limitation])
UNFINISHED = ", ".join(f"'{state}'" for state in UNFINISHED_STATES)
SUMMARY_COLUMNS = (
    "report_id, state, parcel_id, crop_id, analysis_date, created_ts, finished_ts, "
    "error_code, error_message, sources_json, crop_history_json"
)


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


def history_of(text: str | None) -> CropHistory | None:
    return None if text is None else CropHistory.model_validate_json(text)


def record_of(row: sqlite3.Row) -> AnalysisRecord:
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
        sources=PROGRESS.validate_json(row["sources_json"]),
        crop_history=history_of(row["crop_history_json"]),
    )
