"""Deriving a Report: a new Report from stored data, nothing fetched, the source untouched."""

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.contracts.analyses import CropHistory
from app.contracts.report import Report
from app.main import app
from app.orchestrator import runtime, service
from app.orchestrator.service import Orchestrator
from app.orchestrator.sources import get_optional_sources, get_weather_source
from app.sources.parcels import get_parcel_source
from app.storage.reports import ReportStore
from tests.analysis_helpers import NOW, assert_error, start, wait_finished

SAME = {"crop_history": {"same_every_year": True}}
BARE_YEARS = {"crop_history": {"years": {"2015": "bare_field", "2016": "bare_field"}}}


def finished(client, **changes: str) -> str:
    report_id = start(client, **changes)
    assert wait_finished(client, report_id)["state"] == "done"
    return report_id


def report_of(client, report_id: str) -> Report:
    response = client.get(f"/api/reports/{report_id}")
    assert response.status_code == 200, response.text
    return Report.model_validate(response.json())


def derive(client, report_id: str, body: dict = BARE_YEARS):
    return client.post(f"/api/reports/{report_id}/derive", json=body)


def test_derived_report_is_new_and_the_source_stays_byte_for_byte(
    client, uldk, weather, reports_db
):
    source_id = finished(client)
    before = client.get(f"/api/reports/{source_id}").content
    source = report_of(client, source_id)
    fetched = (len(uldk.requests), len(weather.requests))

    response = derive(client, source_id)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"report_id"}
    new_id = response.json()["report_id"]
    assert new_id != source_id and len(new_id) == 22

    new = report_of(client, new_id)
    assert new.meta.report_id == new_id and new.meta.derived_from == source_id
    assert new.meta.created_at > source.meta.created_at
    assert new.meta.model_dump(exclude={"report_id", "created_at", "derived_from"}) == (
        source.meta.model_dump(exclude={"report_id", "created_at", "derived_from"})
    )
    # Same source data: the sources and their fetch times are those of the source Report.
    assert new.sources == source.sources
    assert client.get(f"/api/analyses/{new_id}/status").json()["state"] == "done"

    assert source.historical_course is None
    assert [year.crop.id for year in new.historical_course.years][1:3] == ["bare_field"] * 2
    assert new.multiyear_susceptibility.model_dump(exclude={"history_assumption"}) == (
        source.multiyear_susceptibility.model_dump(exclude={"history_assumption"})
    )
    for part in ("headline", "current_status", "causes", "irrigation", "limitations"):
        assert getattr(new, part) == getattr(source, part), part

    assert client.get(f"/api/reports/{source_id}").content == before
    assert (len(uldk.requests), len(weather.requests)) == fetched
    store = ReportStore(reports_db)
    assert store.inputs(new_id, NOW).source_data == store.inputs(source_id, NOW).source_data
    assert store.get(new_id, NOW).crop_history.years == {2015: "bare_field", 2016: "bare_field"}
    assert store.get(source_id, NOW).crop_history is None


def test_deriving_calls_no_adapter(client, monkeypatch):
    source_id = finished(client)

    def no_adapter():
        raise AssertionError("deriving a report must not fetch anything")

    def no_fetching(*args, **kwargs):
        raise AssertionError("deriving a report must not fetch anything")

    for dependency in (get_parcel_source, get_weather_source, get_optional_sources):
        monkeypatch.setitem(app.dependency_overrides, dependency, no_adapter)
    monkeypatch.setattr(service, "fetch_source_data", no_fetching)
    # The adapters are really blocked: an ordinary analysis cannot even start.
    with pytest.raises(AssertionError, match="must not fetch"):
        start(client)

    response = derive(client, source_id, SAME)
    assert response.status_code == 201, response.text
    new = report_of(client, response.json()["report_id"])
    assert new.historical_course is not None and new.meta.derived_from == source_id


def test_deriving_from_a_derived_report_continues_the_chain(client):
    source_id = finished(client)
    first = derive(client, source_id, SAME).json()["report_id"]
    second = derive(client, first).json()["report_id"]
    assert len({source_id, first, second}) == 3
    assert report_of(client, first).meta.derived_from == source_id
    # The direct source, not the first Report of the chain.
    assert report_of(client, second).meta.derived_from == first
    assert "to potwierdza" in report_of(client, first).multiyear_susceptibility.history_assumption
    assert "w latach 2015, 2016" in (
        report_of(client, second).multiyear_susceptibility.history_assumption
    )


def test_derived_report_survives_a_restart_and_can_be_derived_from(client):
    new_id = derive(client, finished(client)).json()["report_id"]
    before = client.get(f"/api/reports/{new_id}").content
    with TestClient(app) as restarted:
        assert restarted.get(f"/api/reports/{new_id}").content == before
        again = derive(restarted, new_id, SAME)
        assert again.status_code == 201
        assert report_of(restarted, again.json()["report_id"]).meta.derived_from == new_id
        assert restarted.get(f"/api/reports/{new_id}").content == before


def test_unknown_running_and_failed_reports(client, weather):
    assert_error(derive(client, "unknown"), 404, "report_not_found")
    weather.hold = True
    running = start(client)
    assert_error(derive(client, running), 425, "report_not_ready")
    weather.hold = False
    wait_finished(client, running)
    assert derive(client, running).status_code == 201

    weather.status_code = 500
    failed = start(client)
    assert wait_finished(client, failed)["state"] == "failed"
    assert_error(derive(client, failed), 404, "weather_unavailable")


def test_history_is_checked_before_anything_is_computed(client):
    source_id = finished(client)

    def refused(body: dict, status: int, code: str) -> str:
        response = derive(client, source_id, {"crop_history": body})
        assert_error(response, status, code)
        return response.json()["message"]

    message = refused({"years": {"2019": "maize"}}, 422, "unknown_crop")
    assert "2019: maize" in message and "Pszenica ozima, Pole bez uprawy" in message
    message = refused({"years": {"2010": "bare_field", "2024": "winter_wheat"}}, 422,
                      "crop_history_year_outside_window")
    assert "2014–2023" in message and "2010, 2024" in message
    refused({}, 422, "validation_error")
    refused({"years": {"2019": "bare_field"}, "same_every_year": True}, 422, "validation_error")
    refused({"years": {"rok": "bare_field"}}, 422, "validation_error")
    assert_error(client.post(f"/api/reports/{source_id}/derive", json={}), 422, "validation_error")


def test_field_without_a_crop_has_no_history_to_give(client):
    response = derive(client, finished(client, crop_id="bare_field"), SAME)
    assert_error(response, 409, "crop_history_not_applicable")
    assert "Pola bez uprawy" in response.json()["message"]


def test_source_deleted_by_the_retention_cannot_be_derived_from(client, reports_db):
    source_id = finished(client)
    running = runtime.get_orchestrator()
    later = running._clock() + timedelta(days=31)
    running._clock = lambda: later
    assert_error(derive(client, source_id), 404, "report_not_found")

    # The same at the level of the service: no stored data, no Report.
    orchestrator = Orchestrator(ReportStore(reports_db), clock=lambda: later)
    assert asyncio.run(orchestrator.derive(source_id, CropHistory(same_every_year=True))) is None


def test_example_report_keeps_its_stand_in_answer(client):
    response = client.post(
        "/api/reports/demo/derive", json={"crop_history": {"years": {"2019": "maize"}}}
    )
    assert response.status_code == 201
    assert client.get(f"/api/reports/{response.json()['report_id']}").status_code == 200
    assert_error(
        client.post("/api/reports/demo/derive", json={"crop_history": {"years": {"2019": "x"}}}),
        422,
        "unknown_crop",
    )
