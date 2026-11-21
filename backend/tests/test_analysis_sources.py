"""Analysis with soil, terrain, satellite and drought background connected."""

import asyncio
import threading
import time
from dataclasses import replace

from app.catalog.crops import get_crop
from app.contracts.report import Report
from app.engine.params import FALLBACK_AVAILABLE_WATER_MM_PER_M
from app.main import app
from app.orchestrator import params
from app.orchestrator.fetching import time_limit
from app.orchestrator.report_builder import ReportInputs, build_report
from app.orchestrator.runtime import lifespan
from app.orchestrator.service import Orchestrator
from app.orchestrator.sources import AnalysisSources, OptionalSources, SourceSpec, default_specs
from app.sources.soil import NO_ANSWER_TEXT
from app.sources.weather import WeatherSource
from app.storage.reports import ReportStore
from tests.analysis_helpers import NOW, REQUEST, source_states, start, wait_finished
from tests.recorded_sources import Slow, recorded_soil_source, soil_payload_without_water

OPTIONAL_TOPICS = ("soil", "terrain", "satellite", "drought_background")


def finished(client) -> tuple[dict, Report, str]:
    report_id = start(client)
    status = wait_finished(client, report_id)
    assert status["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    return status, report, report_id


def trace_values(report: Report, rule_id: str) -> dict:
    return next(entry.values for entry in report.trace if entry.rule_id == rule_id)


def test_soil_profile_feeds_the_water_balance(client):
    status, report, _ = finished(client)
    capacity = trace_values(report, "root_zone.capacity")
    assert capacity["capacity_source"] == "soil_profile"
    assert capacity["total_available_water_mm"] == 213
    assert capacity["total_available_water_mm"] != FALLBACK_AVAILABLE_WATER_MM_PER_M
    assert report.current_status.details["total_available_water_mm"] == 213
    assert not any("zastępczo" in limitation.text for limitation in report.limitations)
    assert source_states(status) == {
        "weather": "done", "soil": "done", "terrain": "done",
        "satellite": "done", "hydro": "missing",
    }


def test_every_connected_source_is_described_in_the_report(client):
    _, report, _ = finished(client)
    by_topic = {source.topic: source for source in report.sources}
    assert set(by_topic) == {"parcel", "weather", *OPTIONAL_TOPICS}
    for source in by_topic.values():
        assert not source.missing and source.chain_step == 1 and source.fetched_at
        assert source.name != "źródło nieokreślone" and source.license != "nie podano"
    assert by_topic["soil"].name == "ISRIC SoilGrids 2.0"
    assert by_topic["soil"].license.startswith("CC BY 4.0")
    assert by_topic["terrain"].data_date == "2011/2015"
    assert "Sentinel-2" in by_topic["satellite"].name
    assert by_topic["satellite"].data_date == "2023-06-19/2023-06-19"
    drought = by_topic["drought_background"]
    assert (drought.mode, drought.data_date) == ("plik lokalny", "2016-01-01/2023-06-11")
    assert {s.mode for s in report.sources if s.topic != "drought_background"} == {"na żywo"}


def test_stored_source_data_give_the_same_report_again(client, reports_db):
    _, report, report_id = finished(client)
    stored = ReportStore(reports_db).inputs(report_id, NOW)
    again = build_report(
        ReportInputs(
            report_id=report_id,
            created_at=report.meta.created_at,
            source_data=stored.source_data,
            crop=get_crop(stored.record.crop_id),
            analysis_date=stored.record.analysis_date,
            crop_history=stored.record.crop_history,
            source_limitations=tuple(stored.source_limitations),
        )
    )
    assert again == report
    assert again.model_dump_json() == client.get(f"/api/reports/{report_id}").text


def test_soil_layer_without_water_is_named_once(client, optional_sources):
    soil = recorded_soil_source(soil_payload_without_water("60-100cm"))
    optional_sources.current = replace(optional_sources.recorded(), soil=soil)
    status, report, _ = finished(client)
    about_soil = [
        limitation.text
        for limitation in report.limitations
        if not limitation.permanent and "gleb" in limitation.text
    ]
    assert len(about_soil) == 1
    assert about_soil[0].startswith("Dane o glebie obejmują 60 cm z 100 cm")
    assert trace_values(report, "root_zone.capacity")["capacity_source"] == "partial_soil_profile"
    current = report.current_status.confidence
    assert current.level == "średnia"
    assert current.why.count("gleb") == 1
    # The progress note still names the layers the source lacks.
    soil_status = next(source for source in status["sources"] if source["id"] == "soil")
    assert soil_status["state"] == "done" and "60–100 cm" in soil_status["note"]


def test_all_optional_sources_down_gives_the_report_of_weather_alone(
    client, optional_sources, monkeypatch
):
    optional_sources.current = OptionalSources()
    _, alone, _ = finished(client)
    optional_sources.current = OptionalSources(
        soil=recorded_soil_source(status=503), terrain=Slow(), satellite=Slow(),
        drought_background=Slow(),
    )  # fmt: skip
    for name in ("TERRAIN_TIMEOUT_S", "SATELLITE_TIMEOUT_S", "DROUGHT_BACKGROUND_TIMEOUT_S"):
        monkeypatch.setattr(params, name, 0.05)
    status, down, _ = finished(client)
    assert source_states(status) == {
        "weather": "done", "soil": "missing", "terrain": "missing",
        "satellite": "missing", "hydro": "missing",
    }
    notes = {source["id"]: source["note"] for source in status["sources"]}
    assert notes["soil"] == NO_ANSWER_TEXT
    assert "nie odpowiedziało w wyznaczonym czasie" in notes["terrain"]
    assert down.current_status == alone.current_status
    assert down.multiyear_susceptibility == alone.multiyear_susceptibility
    assert down.limitations == alone.limitations
    assert down.trace == alone.trace
    assert {source.topic for source in down.sources if source.missing} == set(OPTIONAL_TOPICS)


def test_slow_optional_sources_end_before_the_budget(reports_db, weather, parcel_source):
    """Limits of the sources are far longer than the budget: the deadline cuts them."""
    budget_s = params.COMPUTE_RESERVE_S + params.SOURCE_DEADLINE_MARGIN_S + 0.4

    async def run() -> tuple[str, float]:
        orchestrator = Orchestrator(ReportStore(reports_db), budget_s=budget_s)
        slow = OptionalSources(
            soil=Slow(), terrain=Slow(), satellite=Slow(), drought_background=Slow()
        )
        specs = default_specs(WeatherSource(transport=weather), slow)
        started = time.monotonic()
        report_id = await orchestrator.start(
            REQUEST, AnalysisSources(parcels=parcel_source, specs=specs)
        )
        while (await orchestrator.status(report_id)).state == "running":
            await asyncio.sleep(0.01)
        return report_id, time.monotonic() - started

    report_id, elapsed_s = asyncio.run(run())
    store = ReportStore(reports_db)
    record = store.get(report_id, NOW)
    assert record.state == "done"
    assert elapsed_s < budget_s - params.COMPUTE_RESERVE_S
    states = {source.id: (source.state, source.note) for source in record.sources}
    assert states["weather"][0] == "done"
    for status_id in ("soil", "terrain", "satellite"):
        assert states[status_id][0] == "missing"
        assert "nie odpowiedziało w wyznaczonym czasie" in states[status_id][1]
    outcomes = store.inputs(report_id, NOW).source_data.outcomes
    assert not next(o for o in outcomes if o.topic == "drought_background").ok


def test_time_limit_of_an_optional_source_ends_before_the_deadline():
    async def fetch(context):
        raise AssertionError("not called")

    optional = SourceSpec(topic="soil", status_id="soil", timeout_s=24.0, fetch=fetch)
    required = replace(optional, topic="weather", status_id="weather", required=True)
    now = time.monotonic()
    assert time_limit(optional, None) == 24.0
    assert time_limit(optional, now + 100.0) == 24.0
    cut = time_limit(optional, now + 10.0)
    assert 8.5 < cut <= 10.0 - params.SOURCE_DEADLINE_MARGIN_S
    assert time_limit(optional, now - 5.0) == 0.0
    assert time_limit(required, now + 10.0) == 24.0


def test_limits_of_the_sources_fit_the_fetch_budget():
    fetch_budget_s = params.ANALYSIS_BUDGET_S - params.COMPUTE_RESERVE_S
    for limit_s in (params.TERRAIN_TIMEOUT_S, params.SATELLITE_TIMEOUT_S, params.SOIL_TIMEOUT_S):
        assert limit_s + params.SOURCE_DEADLINE_MARGIN_S < fetch_budget_s


def test_blocking_work_runs_in_the_sized_thread_pool(reports_db):
    async def worker_name() -> str:
        async with lifespan(app):
            return await asyncio.to_thread(lambda: threading.current_thread().name)

    assert asyncio.run(worker_name()).startswith("analysis")


def test_progress_notes_avoid_the_word_reserved_for_failures():
    notes = (params.SOURCE_ERROR_NOTE, params.SOURCE_TIMEOUT_NOTE, params.SOURCE_NOT_CONNECTED_NOTE)
    for note in notes:
        assert "błąd" not in note.lower() and "ostrzeże" not in note.lower()
