"""Analyses that cannot finish, sources that break, and requests that are refused."""

import asyncio
from dataclasses import replace
from datetime import date, timedelta

import httpx
import pytest

from app.contracts.report import Report
from app.main import app
from app.orchestrator import runtime
from app.orchestrator.service import Orchestrator
from app.orchestrator.sources import (
    AnalysisSources,
    SourceSpec,
    default_specs,
    get_analysis_sources,
)
from app.sources.weather import WeatherSource
from app.storage.reports import ReportStore
from tests.analysis_helpers import (
    ANALYSIS,
    NOW,
    REQUEST,
    assert_error,
    source_states,
    start,
    status_of,
    wait_finished,
)


@pytest.fixture
def use_specs(parcel_source, weather):
    """Replace the source registry of new analyses; restored after the test."""

    def install(change) -> None:
        specs = change(default_specs(WeatherSource(transport=weather)))
        sources = AnalysisSources(parcels=parcel_source, specs=tuple(specs))
        app.dependency_overrides[get_analysis_sources] = lambda: sources

    yield install
    app.dependency_overrides.pop(get_analysis_sources, None)


def failed_report(client, report_id: str, code: str) -> dict:
    assert wait_finished(client, report_id)["state"] == "failed"
    response = client.get(f"/api/reports/{report_id}")
    assert_error(response, 404, code)
    return response.json()


def test_parcel_that_does_not_exist_fails_the_analysis(client, weather):
    report_id = start(client, parcel_id="040704_2.0020.99999")
    body = failed_report(client, report_id, "parcel_unavailable")
    assert "Działka o takim identyfikatorze nie istnieje." in body["message"]
    assert weather.requests == []
    assert source_states(status_of(client, report_id))["weather"] == "missing"


def test_parcel_service_down_fails_the_analysis(client, uldk):
    uldk.failure = httpx.ConnectError("down")
    body = failed_report(client, start(client), "parcel_unavailable")
    assert "nie odpowiedziała" in body["message"]


def test_weather_archive_down_fails_the_analysis_with_a_reason(client, weather):
    weather.status_code = 503
    report_id = start(client)
    body = failed_report(client, report_id, "weather_unavailable")
    assert "brak danych pogodowych" in body["message"]
    weather_status = status_of(client, report_id)["sources"][0]
    assert (weather_status["id"], weather_status["state"]) == ("weather", "missing")
    assert weather_status["note"]


def test_slow_weather_is_cut_at_its_own_time_limit(client, weather, use_specs):
    use_specs(lambda specs: [replace(specs[0], timeout_s=0.05), *specs[1:]])
    weather.hold = True
    report_id = start(client)
    failed_report(client, report_id, "weather_unavailable")
    note = status_of(client, report_id)["sources"][0]["note"]
    assert "nie odpowiedziało w wyznaczonym czasie" in note
    weather.hold = False


@pytest.mark.parametrize("problem", ["raises", "too_slow"])
def test_broken_optional_source_does_not_stop_the_analysis(client, use_specs, problem):
    async def broken_soil(context):
        if problem == "raises":
            raise RuntimeError("boom")
        await asyncio.sleep(30)

    def with_soil(specs):
        soil = SourceSpec(topic="soil", status_id="soil", timeout_s=0.05, fetch=broken_soil)
        return [soil if spec.topic == "soil" else spec for spec in specs]

    use_specs(with_soil)
    report_id = start(client)
    status = wait_finished(client, report_id)
    assert status["state"] == "done"
    assert source_states(status) == {
        "weather": "done", "soil": "missing", "terrain": "missing",
        "satellite": "missing", "hydro": "missing",
    }
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    soil = next(source for source in report.sources if source.topic == "soil")
    assert soil.missing and soil.chain_step == 1
    assert any("Brak danych o glebie" in limitation.text for limitation in report.limitations)


def test_whole_analysis_is_cut_at_the_time_budget(reports_db, weather, parcel_source):
    async def run() -> str:
        orchestrator = Orchestrator(ReportStore(reports_db), budget_s=3.05)
        specs = default_specs(WeatherSource(transport=weather))
        sources = AnalysisSources(parcels=parcel_source, specs=specs)
        report_id = await orchestrator.start(REQUEST, sources)
        while (await orchestrator.status(report_id)).state == "running":
            await asyncio.sleep(0.01)
        return report_id

    weather.hold = True
    report_id = asyncio.run(run())
    record = ReportStore(reports_db).get(report_id, NOW)
    assert (record.state, record.error_code) == ("failed", "analysis_timeout")
    assert record.sources[0].state == "missing"


def test_request_is_checked_before_anything_starts(client, weather, uldk, monkeypatch):
    def refused(code: str, **changes) -> None:
        assert_error(client.post("/api/analyses", json={**ANALYSIS, **changes}), 422, code)

    refused("unknown_crop", crop_id="x")
    # A crop that exists, but is not on the closed list.
    response = client.post("/api/analyses", json={**ANALYSIS, "crop_id": "soybean"})
    assert_error(response, 422, "unknown_crop")
    assert "z listy" in response.json()["message"]
    refused("invalid_parcel_id", parcel_id="Krusza Podlotowa 34/2")
    refused("validation_error", analysis_date="20.06.2023")

    monkeypatch.setattr(runtime, "local_today", lambda: date(2026, 11, 21))
    refused("analysis_date_in_future", analysis_date="2026-11-22")
    assert client.post(
        "/api/analyses", json={**ANALYSIS, "analysis_date": "2026-11-21"}
    ).status_code == 202
    assert len(uldk.requests) == 1 and len(weather.requests) <= 1


def test_today_is_the_local_day(monkeypatch):
    assert abs(runtime.local_today() - date.today()) <= timedelta(days=1)


def test_simulation_waits_for_the_report_and_then_answers(client, weather):
    weather.hold = True
    report_id = start(client)
    ranking = f"/api/reports/{report_id}/simulation/ranking"
    assert_error(client.get(ranking), 425, "report_not_ready")
    weather.hold = False
    wait_finished(client, report_id)
    # The simulation is real: it answers for a Report of an analysis and knows
    # only the crops of the crop list.
    assert client.get(ranking).status_code == 200
    compare = client.get(
        f"/api/reports/{report_id}/simulation/compare", params={"crop_id": "soybean"}
    )
    assert_error(compare, 422, "unknown_crop")
    assert_error(client.get("/api/reports/unknown/simulation/ranking"), 404, "report_not_found")
