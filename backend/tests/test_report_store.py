"""Report store: one SQLite file, immutable Reports, retention, restart."""

import sqlite3
from datetime import timedelta

import pytest

from app.catalog.crops import get_crop
from app.contracts.analyses import CropHistory, SourceProgress
from app.contracts.report import Limitation
from app.orchestrator.report_builder import ReportInputs, build_report
from app.storage.reports import AnalysisNotOpenError, ReportStore
from tests.analysis_helpers import ANALYSIS_DATE, NOW, REQUEST, stored_source_data

SOURCES = [SourceProgress(id="weather", state="wait")]
DONE = [SourceProgress(id="weather", state="done")]
LIMITATION = Limitation(text="Luka w danych.", affects="current", permanent=False)


@pytest.fixture
def store(tmp_path) -> ReportStore:
    return ReportStore(tmp_path / "nested" / "reports.sqlite3", retention=timedelta(days=30))


def report_for(report_id: str):
    inputs = ReportInputs(
        report_id=report_id,
        created_at=NOW,
        source_data=stored_source_data(),
        crop=get_crop("winter_wheat"),
        analysis_date=ANALYSIS_DATE,
    )
    return build_report(inputs)


def finish(store: ReportStore, report_id: str = "r1"):
    store.create(report_id, REQUEST, SOURCES, NOW)
    store.begin_finalize(report_id)
    report = report_for(report_id)
    store.save_report(report, stored_source_data(), [LIMITATION], DONE, NOW)
    return report


def test_started_analysis_is_running_and_has_no_report(store):
    store.create("r1", REQUEST, SOURCES, NOW)
    record = store.get("r1", NOW)
    assert (record.state, record.finished, record.sources) == ("running", False, SOURCES)
    assert (record.parcel_id, record.crop_id) == (REQUEST.parcel_id, "winter_wheat")
    assert (record.analysis_date, record.created_at) == (ANALYSIS_DATE, NOW)
    assert store.report_json("r1", NOW) is None
    assert store.inputs("r1", NOW) is None
    assert store.get("unknown", NOW) is None


def test_report_is_stored_with_everything_it_was_computed_from(store):
    report = finish(store)
    assert store.report_json("r1", NOW) == report.model_dump_json()
    record = store.get("r1", NOW)
    assert (record.state, record.sources, record.finished_at) == ("done", DONE, NOW)
    inputs = store.inputs("r1", NOW)
    assert inputs.source_data == stored_source_data()
    assert inputs.source_limitations == [LIMITATION]
    assert inputs.record.crop_id == "winter_wheat"


def test_stored_report_cannot_be_changed(store):
    report = finish(store)
    assert not store.set_crop_history("r1", CropHistory(same_every_year=True))
    assert not store.save_failure("r1", "analysis_failed", "x", DONE, NOW)
    assert store.fail_unfinished("analysis_interrupted", "x", NOW) == 0
    with pytest.raises(AnalysisNotOpenError):
        store.save_report(report_for("r1"), stored_source_data(), [], DONE, NOW)
    with pytest.raises(AnalysisNotOpenError):
        store.begin_finalize("r1")
    # Even a direct statement against the file is refused by the database.
    with sqlite3.connect(store._path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE analyses SET report_json = '{}' WHERE report_id = 'r1'")
    assert store.report_json("r1", NOW) == report.model_dump_json()


def test_crop_history_is_accepted_only_while_running(store):
    history = CropHistory(years={2019: "winter_wheat"})
    assert not store.set_crop_history("unknown", history)
    store.create("r1", REQUEST, SOURCES, NOW)
    assert store.set_crop_history("r1", history)
    assert store.get("r1", NOW).crop_history == history
    assert store.begin_finalize("r1") == history
    assert not store.set_crop_history("r1", CropHistory(same_every_year=True))
    assert store.get("r1", NOW).crop_history == history


def test_failure_is_recorded_once(store):
    store.create("r1", REQUEST, SOURCES, NOW)
    missing = [SourceProgress(id="weather", state="missing", note="Brak odpowiedzi.")]
    assert store.save_failure("r1", "weather_unavailable", "Brak pogody.", missing, NOW)
    record = store.get("r1", NOW)
    assert (record.state, record.error_code, record.error_message) == (
        "failed", "weather_unavailable", "Brak pogody.",
    )
    assert record.sources == missing
    assert not store.save_failure("r1", "analysis_failed", "x", SOURCES, NOW)


def test_new_store_object_on_the_same_file_reads_the_report(store):
    report = finish(store)
    reopened = ReportStore(store._path)
    assert reopened.report_json("r1", NOW) == report.model_dump_json()


def test_unfinished_analyses_are_closed_after_a_restart(store):
    finish(store, "done")
    store.create("running", REQUEST, SOURCES, NOW)
    store.create("finalizing", REQUEST, SOURCES, NOW)
    store.begin_finalize("finalizing")
    reopened = ReportStore(store._path)
    assert reopened.fail_unfinished("analysis_interrupted", "Przerwano.", NOW) == 2
    for report_id in ("running", "finalizing"):
        record = reopened.get(report_id, NOW)
        assert (record.state, record.error_code) == ("failed", "analysis_interrupted")
    assert reopened.get("done", NOW).state == "done"


def test_reports_disappear_after_the_retention_time(store):
    finish(store, "old")
    later = NOW + timedelta(days=30, seconds=1)
    store.create("new", REQUEST, SOURCES, later)
    # Expired reports are invisible even before they are deleted.
    assert store.get("old", NOW + timedelta(days=29)) is not None
    assert store.get("old", later) is None
    assert store.report_json("old", later) is None
    assert store.inputs("old", later) is None
    assert store.purge_expired(later) == 1
    assert store.purge_expired(later) == 0
    with sqlite3.connect(store._path) as connection:
        assert connection.execute("SELECT report_id FROM analyses").fetchall() == [("new",)]
