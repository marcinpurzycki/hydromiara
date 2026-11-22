"""Whole analysis with the water adapter connected: Report parts, failures, the local copy."""

from dataclasses import replace

import pytest

from app.contracts.report import Report
from app.engine.source_limitations import TOPICS
from app.orchestrator import params
from app.sources import hydro_params
from app.sources.hydro import HydroSource
from app.storage.reports import ReportStore
from tests.analysis_helpers import NOW, source_states, start, wait_finished
from tests.hydro_helpers import (
    ClassFileServer,
    live_link,
    local_link,
    recorded_hydro_source,
    write_class_files,
)
from tests.recorded_sources import Broken, Slow
from tests.soil_helpers import category_answer, recorded_soil_source

DITCH_RULE = "recommendation.ditch_water_retention"
MISSING = TOPICS["hydro"].missing_text
INCOMPLETE = "Publiczne dane o rowach i ciekach są niekompletne."


def run(client, optional_sources, hydro) -> tuple[dict, Report, str]:
    # A soil of category IV: one year of the window is then without a deficit and in the
    # other nine precipitation covers less than half of the evaporation, which is the
    # cause the ditch recommendation answers.
    soil = recorded_soil_source(category=category_answer(4))
    optional_sources.current = replace(optional_sources.recorded(), hydro=hydro, soil=soil)
    report_id = start(client)
    status = wait_finished(client, report_id)
    assert status["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    return status, report, report_id


def texts(report: Report) -> list[str]:
    return [limitation.text for limitation in report.limitations]


def trace_result(report: Report, rule_id: str) -> str:
    return next(entry.result for entry in report.trace if entry.rule_id == rule_id)


def test_waters_reach_the_report_the_map_and_the_stored_source_data(
    client, optional_sources, tmp_path, reports_db
):
    status, report, report_id = run(client, optional_sources, recorded_hydro_source(tmp_path))
    assert source_states(status)["hydro"] == "done"
    source = next(item for item in report.sources if item.topic == "hydro")
    assert source.name == hydro_params.BDOT_SOURCE_NAME and source.chain_step == 1
    assert not source.missing and source.mode == "na żywo" and source.data_date == "2026-11-21"
    assert "bezpłatnie" in source.license
    assert [(item.kind, item.name) for item in report.map.water_objects] == [
        ("ditch", None), ("water_body", None),
        ("watercourse", "Struga Testowa"), ("watercourse", "Rzeka Szeroka"),
    ]  # fmt: skip
    stored = ReportStore(reports_db).inputs(report_id, NOW).source_data
    assert len(stored.hydro.objects) == 4
    assert [item.geometry for item in stored.hydro.objects] == [
        item.geometry for item in report.map.water_objects
    ]
    listed = texts(report)
    assert MISSING not in listed and sum(INCOMPLETE in text for text in listed) == 1
    for text in hydro_params.SCOPE_LIMITATIONS:
        assert listed.count(text) == 1
    # Limitations about recommendations leave the confidence of the verdicts alone.
    assert "BDOT10k" not in report.current_status.confidence.why


def test_ditch_at_the_parcel_gives_a_recommendation_with_a_retention_site(
    client, optional_sources, tmp_path
):
    _, report, _ = run(client, optional_sources, recorded_hydro_source(tmp_path))
    found = [item for cause in report.causes for item in cause.recommendations]
    ditch = next(item for item in found if item.id == "ditch_water_retention")
    assert "rów melioracyjny (10 m od granicy Działki, strona wschodnia)" in ditch.text
    assert ditch.inputs["ditch_distance_m"] == 10
    assert report.map.retention_sites == [ditch.retention_site]
    assert ditch.retention_site.geometry.type == "LineString"
    assert trace_result(report, DITCH_RULE).startswith("uruchomiono")
    assert "rów melioracyjny (10 m od granicy Działki" in trace_result(report, "water.nearest")


def test_without_a_ditch_in_the_data_no_ditch_recommendation_appears(
    client, optional_sources, tmp_path
):
    server = ClassFileServer(write_class_files(tmp_path / "empty", objects={}))
    _, report, _ = run(client, optional_sources, HydroSource(links=[live_link(server)]))
    assert report.map.water_objects == [] and report.map.retention_sites == []
    assert trace_result(report, DITCH_RULE) == "nie uruchomiono: warunek niespełniony"
    assert "nie ma rowów" in trace_result(report, "water.nearest")
    assert MISSING not in texts(report)
    assert next(item for item in report.sources if item.topic == "hydro").missing is False


@pytest.mark.parametrize("problem", [Broken, Slow])
def test_broken_or_slow_waters_do_not_stop_the_analysis(
    client, optional_sources, problem, monkeypatch
):
    monkeypatch.setattr(params, "HYDRO_TIMEOUT_S", 0.05)
    status, report, _ = run(client, optional_sources, problem())
    hydro = next(item for item in status["sources"] if item["id"] == "hydro")
    assert hydro["state"] == "missing" and hydro["note"]
    others = [item for item in status["sources"] if item["id"] != "hydro"]
    assert all(item["state"] == "done" for item in others)
    source = next(item for item in report.sources if item.topic == "hydro")
    assert source.missing and source.name == hydro_params.BDOT_SOURCE_NAME
    assert texts(report).count(MISSING) == 1
    assert report.map.water_objects == [] and report.map.retention_sites == []
    assert trace_result(report, DITCH_RULE).startswith("nie uruchomiono: brak danych")
    for text in hydro_params.SCOPE_LIMITATIONS:
        assert text not in texts(report)


def test_failed_live_read_without_a_copy_is_reported_as_missing(
    client, optional_sources, tmp_path
):
    server = ClassFileServer(write_class_files(tmp_path / "remote"))
    server.status = 503
    status, report, _ = run(client, optional_sources, HydroSource(links=[live_link(server)]))
    hydro = next(item for item in status["sources"] if item["id"] == "hydro")
    assert hydro["state"] == "missing" and hydro["note"].startswith(hydro_params.NO_DATA)
    assert texts(report).count(MISSING) == 1


def test_local_copy_replaces_a_failed_live_read_and_the_report_says_so(
    client, optional_sources, tmp_path
):
    server = ClassFileServer(write_class_files(tmp_path / "remote"))
    server.status = 503
    chain = HydroSource(links=[live_link(server), local_link(tmp_path / "copy")])
    status, report, _ = run(client, optional_sources, chain)
    assert source_states(status)["hydro"] == "done"
    source = next(item for item in report.sources if item.topic == "hydro")
    assert source.chain_step == 2 and source.mode == "plik lokalny" and not source.missing
    assert source.name == hydro_params.BDOT_LOCAL_SOURCE_NAME
    stepped = [text for text in texts(report) if "z mniej dokładnego zamiennika" in text]
    assert len(stepped) == 1 and "Rekomendacje dotyczące rowów i cieków" in stepped[0]
    assert len(report.map.water_objects) == 4 and MISSING not in texts(report)
