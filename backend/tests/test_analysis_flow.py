"""Full path through the API: start, progress, Report, crop history, restart, retention."""

import logging
import sqlite3
from datetime import timedelta

from fastapi.testclient import TestClient

from app.contracts.report import Report
from app.contracts.source_data import SourceData
from app.main import app
from app.orchestrator import service
from app.storage.reports import ReportStore
from tests.analysis_helpers import (
    ANALYSIS,
    NOW,
    PARCEL_ID,
    REQUEST,
    assert_error,
    source_states,
    start,
    status_of,
    wait_finished,
)

SOURCE_ORDER = ["weather", "soil", "terrain", "satellite", "hydro"]
# The drought background is stored and listed in the Report without a progress entry.
STORED_TOPICS = ["parcel", "weather", "soil", "terrain", "satellite", "drought_background"]


def test_analysis_runs_in_the_background_then_the_report_is_ready(client, weather):
    weather.hold = True
    report_id = start(client)

    running = status_of(client, report_id)
    assert running["state"] == "running"
    assert [source["id"] for source in running["sources"]] == SOURCE_ORDER
    assert source_states(running)["weather"] in ("wait", "run")
    assert_error(client.get(f"/api/reports/{report_id}"), 425, "report_not_ready")

    weather.hold = False
    done = wait_finished(client, report_id)
    assert done["state"] == "done"
    assert source_states(done)["weather"] == "done"

    response = client.get(f"/api/reports/{report_id}")
    assert response.status_code == 200
    report = Report.model_validate(response.json())
    assert report.meta.report_id == report_id
    assert report.meta.parcel.parcel_id == PARCEL_ID
    assert report.meta.parcel.area_ha > 0
    assert report.meta.analysis_date.isoformat() == ANALYSIS["analysis_date"]
    assert report.multiyear_susceptibility.total_years == 10
    assert [source.topic for source in report.sources] == STORED_TOPICS


def test_source_that_is_not_connected_is_missing_from_the_start(client, weather):
    weather.hold = True
    report_id = start(client)
    while_running = status_of(client, report_id)
    weather.hold = False
    finished = wait_finished(client, report_id)
    for status in (while_running, finished):
        hydro = next(source for source in status["sources"] if source["id"] == "hydro")
        assert hydro["state"] == "missing"
        assert "nie jest jeszcze używane" in hydro["note"]
    assert source_states(finished) == {
        "weather": "done", "soil": "done", "terrain": "done",
        "satellite": "done", "hydro": "missing",
    }


def test_unknown_report(client):
    assert_error(client.get("/api/analyses/unknown/status"), 404, "report_not_found")
    assert_error(client.get("/api/reports/unknown"), 404, "report_not_found")
    history = {"same_every_year": True}
    assert_error(
        client.put("/api/analyses/unknown/crop-history", json=history), 404, "report_not_found"
    )


def test_report_is_immutable_and_reading_computes_nothing(client, weather, uldk, monkeypatch):
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    first = client.get(f"/api/reports/{report_id}")
    fetched = (len(weather.requests), len(uldk.requests))
    assert fetched == (1, 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("a stored report must not be computed again")

    monkeypatch.setattr(service, "build_report", forbidden)
    for _ in range(3):
        again = client.get(f"/api/reports/{report_id}")
        assert again.status_code == 200
        assert again.content == first.content
        assert status_of(client, report_id)["state"] == "done"
    assert (len(weather.requests), len(uldk.requests)) == fetched


def test_each_analysis_gets_its_own_unguessable_identifier(client):
    ids = {start(client) for _ in range(20)}
    assert len(ids) == 20
    # 16 random bytes as URL-safe text; no identifier is derived from the request.
    assert all(len(report_id) == 22 for report_id in ids)
    assert not any(PARCEL_ID in report_id for report_id in ids)
    assert service.new_report_id() != service.new_report_id()
    for report_id in ids:
        wait_finished(client, report_id)


def test_crop_history_is_accepted_while_running_and_refused_afterwards(
    client, weather, reports_db
):
    weather.hold = True
    report_id = start(client)
    url = f"/api/analyses/{report_id}/crop-history"
    assert client.put(url, json={"same_every_year": True}).status_code == 204
    history = {"years": {"2019": "winter_wheat", "2020": "bare_field"}}
    assert client.put(url, json=history).status_code == 204
    assert_error(client.put(url, json={"years": {"2019": "maize"}}), 422, "unknown_crop")
    assert_error(client.put(url, json={}), 422, "validation_error")

    weather.hold = False
    assert wait_finished(client, report_id)["state"] == "done"
    assert_error(client.put(url, json={"same_every_year": True}), 409, "analysis_finished")
    # The history given last while running is the one kept with the Report.
    stored = ReportStore(reports_db).get(report_id, NOW)
    assert stored.crop_history.years == {2019: "winter_wheat", 2020: "bare_field"}


def test_source_data_are_stored_completely_with_the_report(client, reports_db):
    report_id = start(client)
    wait_finished(client, report_id)
    inputs = ReportStore(reports_db).inputs(report_id, NOW)
    assert isinstance(inputs.source_data, SourceData)
    assert inputs.source_data.parcel.parcel_id == PARCEL_ID
    assert len(inputs.source_data.weather.days) > 3900
    assert inputs.source_data.weather.days[-1].date.isoformat() == ANALYSIS["analysis_date"]
    assert [outcome.topic for outcome in inputs.source_data.outcomes] == STORED_TOPICS
    assert all(outcome.ok for outcome in inputs.source_data.outcomes)
    assert len(inputs.source_data.soil.layers) == 5
    assert inputs.source_data.terrain.elevations_m
    assert inputs.source_data.satellite.scenes[-1].date.isoformat() == "2023-06-19"
    assert inputs.source_data.drought_background.dekads[-1].date.isoformat() == "2023-06-11"
    assert inputs.source_data.hydro is None


def test_report_survives_a_restart(client, weather, uldk):
    report_id = start(client)
    wait_finished(client, report_id)
    before = client.get(f"/api/reports/{report_id}").content
    with TestClient(app) as restarted:
        assert restarted.get(f"/api/reports/{report_id}").content == before
        assert status_of(restarted, report_id)["state"] == "done"
    assert (len(weather.requests), len(uldk.requests)) == (1, 1)


def test_analysis_cut_by_a_restart_is_failed_not_running_forever(reports_db):
    store = ReportStore(reports_db)
    store.create("left-running", REQUEST, [], NOW)
    with TestClient(app) as restarted:
        assert status_of(restarted, "left-running")["state"] == "failed"
        assert_error(restarted.get("/api/reports/left-running"), 404, "analysis_interrupted")
        assert_error(
            restarted.put("/api/analyses/left-running/crop-history", json={"same_every_year": True}),
            409,
            "analysis_finished",
        )


def test_analysis_running_at_shutdown_is_closed_as_interrupted(reports_db, weather):
    weather.hold = True
    with TestClient(app) as running:
        report_id = start(running)
        assert status_of(running, report_id)["state"] == "running"
    record = ReportStore(reports_db).get(report_id, NOW)
    assert (record.state, record.error_code) == ("failed", "analysis_interrupted")


def test_expired_reports_are_deleted_on_start(reports_db):
    store = ReportStore(reports_db)
    store.create("old", REQUEST, [], NOW - timedelta(days=4000))
    with TestClient(app) as running:
        assert_error(running.get("/api/reports/old"), 404, "report_not_found")
    with sqlite3.connect(reports_db) as connection:
        assert connection.execute("SELECT count(*) FROM analyses").fetchone() == (0,)


def test_duration_of_every_source_goes_to_the_log(client, caplog):
    caplog.set_level(logging.INFO, logger="hydromiara.analysis")
    report_id = start(client)
    wait_finished(client, report_id)
    lines = [record.getMessage() for record in caplog.records]
    for topic in ("parcel", "weather"):
        assert any(f"source={topic} ok=True duration_s=" in line for line in lines)
    assert any("finished state=done total_s=" in line for line in lines)
    # The identifier is the key to the Report, so the log holds only its beginning.
    assert not any(report_id in line for line in lines)
