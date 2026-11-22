"""The summary on the whole analysis path: provider off, on, failing, slow; derived Reports."""

import asyncio
import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.catalog.crops import get_crop
from app.contracts.report import Report
from app.main import app
from app.orchestrator import params, runtime
from app.orchestrator.report_builder import ReportInputs, build_report
from app.orchestrator.service import Orchestrator
from app.orchestrator.sources import AnalysisSources, default_specs
from app.sources.weather import WeatherSource
from app.storage.reports import ReportStore
from app.summary.service import RULE_ID
from app.summary.template import template_summary
from tests.analysis_helpers import NOW, PARCEL_ID, REQUEST, start, wait_finished
from tests.summary_helpers import KEY, MODEL, RecordedModel, sent_data, summarizer

SAME_EVERY_YEAR = {"crop_history": {"same_every_year": True}}


@pytest.fixture
def model(monkeypatch) -> RecordedModel:
    """A configured provider answered by the recorded model instead of the network."""
    recorded = RecordedModel()
    monkeypatch.setattr(runtime, "build_summarizer", lambda: summarizer(recorded))
    return recorded


@pytest.fixture
def llm_client(model, reports_db):
    with TestClient(app) as running:
        yield running


def finished(client, **changes) -> tuple[str, bytes, Report]:
    report_id = start(client, **changes)
    assert wait_finished(client, report_id)["state"] == "done"
    response = client.get(f"/api/reports/{report_id}")
    assert response.status_code == 200
    return report_id, response.content, Report.model_validate(response.json())


def summary_entries(report: Report) -> list:
    return [entry for entry in report.trace if entry.rule_id == RULE_ID]


def test_provider_switched_off_gives_a_complete_report_with_the_template(client, reports_db):
    report_id, _, report = finished(client)
    assert report.summary.source == "template"
    assert report.summary == template_summary(report)
    assert report.headline in report.summary.text
    assert summary_entries(report) == []
    assert not any("nie wyznacza jeszcze" in item.text for item in report.limitations)
    # Every part of the Report is there, and it is exactly what the stored data give again.
    assert report.causes and report.irrigation.text and report.consistency_check.sentence
    stored = ReportStore(reports_db).inputs(report_id, NOW)
    inputs = ReportInputs(
        report_id=report_id,
        created_at=report.meta.created_at,
        source_data=stored.source_data,
        crop=get_crop("winter_wheat"),
        analysis_date=report.meta.analysis_date,
        source_limitations=tuple(stored.source_limitations),
    )
    assert build_report(inputs) == report


def test_accepted_answer_is_stored_with_the_report_and_never_asked_for_again(
    llm_client, model, reports_db, caplog
):
    caplog.set_level(logging.DEBUG)
    report_id, raw, report = finished(llm_client)
    assert report.summary.source == "llm"
    assert report.summary.text.startswith(report.headline)
    assert report.summary != template_summary(report)
    (entry,) = summary_entries(report)
    assert entry == report.trace[-1] and entry.result == "llm"
    assert entry.values == {"fallback_reason": None, "model": MODEL}
    # The stored Report does not change: reading it again asks nobody and gives the same bytes.
    assert llm_client.get(f"/api/reports/{report_id}").content == raw
    assert len(model.requests) == 1
    # Only the result went out: nothing that identifies the parcel or the Report.
    sent = model.requests[0].content.decode()
    parcel = report.meta.parcel
    for secret in (PARCEL_ID, parcel.number, parcel.region, parcel.commune, parcel.county,
                   parcel.voivodeship, report_id, "coordinates", "18.2", "52.7"):
        assert secret not in sent, secret
    assert sent_data(model.requests[0])["naglowek"] == report.headline
    # The key stays in the request header: not in the log, the Report or the database.
    assert model.requests[0].headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in caplog.text and KEY not in raw.decode()
    assert KEY.encode() not in reports_db.read_bytes()
    assert "summary source=llm fallback_reason=None" in caplog.text
    assert report.summary.text not in caplog.text


@pytest.mark.parametrize(
    ("prepare", "reason"),
    [
        (lambda m: setattr(m, "status_code", 500), "provider_error"),
        (lambda m: setattr(m, "status_code", 401), "provider_auth"),
        (lambda m: setattr(m, "raw_body", "<html>"), "provider_bad_answer"),
        (lambda m: setattr(m, "answer", "Wody zabraknie za 5 dni, a ryzyko suszy rośnie." * 2),
         "number_not_in_report"),
    ],
)
def test_failing_provider_never_fails_the_analysis(llm_client, model, prepare, reason):
    prepare(model)
    _, _, report = finished(llm_client)
    assert report.summary == template_summary(report)
    (entry,) = summary_entries(report)
    assert entry.result == "template"
    assert entry.values == {"fallback_reason": reason, "model": MODEL}
    assert len(model.requests) == 1


def test_derived_report_keeps_the_template_and_calls_nobody(llm_client, model):
    source_id, raw, source = finished(llm_client)
    assert source.summary.source == "llm" and len(model.requests) == 1
    response = llm_client.post(f"/api/reports/{source_id}/derive", json=SAME_EVERY_YEAR)
    assert response.status_code == 201, response.text
    derived = Report.model_validate(
        llm_client.get(f"/api/reports/{response.json()['report_id']}").json()
    )
    assert derived.meta.derived_from == source_id and derived.historical_course is not None
    assert derived.summary == template_summary(derived)
    assert summary_entries(derived) == []
    assert len(model.requests) == 1
    assert llm_client.get(f"/api/reports/{source_id}").content == raw


def test_critical_period_analysis_is_a_fresh_analysis_with_its_own_summary(llm_client, model):
    source_id, _, _ = finished(llm_client, analysis_date="2023-11-15")
    response = llm_client.post(f"/api/reports/{source_id}/critical-period")
    assert response.status_code == 202, response.text
    new_id = response.json()["report_id"]
    assert wait_finished(llm_client, new_id)["state"] == "done"
    new = Report.model_validate(llm_client.get(f"/api/reports/{new_id}").json())
    assert new.summary.source == "llm" and new.summary.text.startswith(new.headline)
    assert len(model.requests) == 2


def test_slow_provider_is_cut_inside_the_time_budget(reports_db, weather, parcel_source):
    """The provider's own limit is far longer than what the analysis has left."""
    budget_s = params.COMPUTE_RESERVE_S + 0.6
    slow = RecordedModel()
    slow.delay_s = 60.0

    async def run() -> tuple[str, float]:
        orchestrator = Orchestrator(
            ReportStore(reports_db), budget_s=budget_s, summarizer=summarizer(slow, timeout_s=60.0)
        )
        specs = default_specs(WeatherSource(transport=weather))
        started = time.monotonic()
        report_id = await orchestrator.start(
            REQUEST, AnalysisSources(parcels=parcel_source, specs=specs)
        )
        while (await orchestrator.status(report_id)).state == "running":
            await asyncio.sleep(0.01)
        return report_id, time.monotonic() - started

    report_id, took_s = asyncio.run(run())
    assert took_s < budget_s
    assert took_s > budget_s - params.SAVE_RESERVE_S - 0.5  # it did wait for the model
    store = ReportStore(reports_db)
    assert store.get(report_id, NOW).state == "done"
    report = Report.model_validate_json(store.report_json(report_id, NOW))
    assert report.summary == template_summary(report)
    (entry,) = summary_entries(report)
    assert entry.values["fallback_reason"] == "provider_timeout"
    assert len(slow.requests) == 1
