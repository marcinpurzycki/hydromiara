"""Each optional source broken, too slow or without data: the analysis still ends."""

from dataclasses import replace

import httpx
import pytest

from app.contracts.report import Report
from app.orchestrator import params
from app.sources.drought_background import DroughtBackgroundSource
from app.sources.satellite import SatelliteSource
from app.sources.satellite_providers import EARTH_SEARCH
from app.engine.soil_limitations import NO_CATEGORY_TEXT, NO_SOIL_TEXT, ORGANIC_TEXT
from app.storage.reports import ReportStore
from tests.analysis_helpers import NOW, start, wait_finished
from tests.recorded_sources import Broken, Slow, recorded_terrain_source
from tests.soil_helpers import point_answer, recorded_soil_source

LIMITS = {
    "soil": "SOIL_TIMEOUT_S",
    "terrain": "TERRAIN_TIMEOUT_S",
    "satellite": "SATELLITE_TIMEOUT_S",
    "drought_background": "DROUGHT_BACKGROUND_TIMEOUT_S",
}
# Start of the limitation the engine writes when the category has no data.
MISSING_TEXT = {
    "soil": "Nie udało się pobrać danych o glebie",
    "terrain": "Brak danych o ukształtowaniu terenu",
    "satellite": "Brak odczytów satelitarnych",
    "drought_background": "Brak niezależnego wskaźnika suszy",
}
# Confidence of (current status, multi-year susceptibility) without the category.
# The other sources answer from the recordings, where the satellite windows of
# earlier years have no scene: one limitation of the multi-year confidence.
CONFIDENCE = {
    "soil": ("średnia", "niska"),
    "terrain": ("wysoka", "średnia"),
    "satellite": ("średnia", "średnia"),
    "drought_background": ("średnia", "średnia"),
}


def run(client, reports_db) -> tuple[dict, Report, dict]:
    report_id = start(client)
    status = wait_finished(client, report_id)
    assert status["state"] == "done"
    report = Report.model_validate(client.get(f"/api/reports/{report_id}").json())
    stored = ReportStore(reports_db).inputs(report_id, NOW).source_data
    return status, report, {outcome.topic: outcome for outcome in stored.outcomes}


def check_missing(topic: str, status: dict, report: Report, outcomes: dict) -> str:
    """The category is missing everywhere it is shown; returns the recorded reason."""
    assert not outcomes[topic].ok and outcomes[topic].message
    source = next(source for source in report.sources if source.topic == topic)
    assert source.missing and source.chain_step == 1
    assert source.name != "źródło nieokreślone"
    named = [text for text in (l.text for l in report.limitations) if MISSING_TEXT[topic] in text]
    assert len(named) == 1
    levels = (
        report.current_status.confidence.level,
        report.multiyear_susceptibility.confidence.level,
    )
    assert levels == CONFIDENCE[topic]
    states = {item["id"]: item for item in status["sources"]}
    if topic in states:
        assert states[topic]["state"] == "missing"
        assert states[topic]["note"] == outcomes[topic].message
    others = [item for item in status["sources"] if item["id"] not in (topic, "hydro")]
    assert all(item["state"] == "done" for item in others)
    return outcomes[topic].message


@pytest.mark.parametrize("topic", list(LIMITS))
@pytest.mark.parametrize("problem", [Broken, Slow])
def test_one_source_broken_or_too_slow(
    client, reports_db, optional_sources, monkeypatch, topic, problem
):
    monkeypatch.setattr(params, LIMITS[topic], 0.05)
    monkeypatch.setattr(params, "ADAPTER_GRACE_S", 0.0)
    optional_sources.current = replace(optional_sources.recorded(), **{topic: problem()})
    reason = check_missing(topic, *run(client, reports_db))
    if problem is Slow:
        assert reason == "Źródło nie odpowiedziało w wyznaczonym czasie (0 s)."
    else:
        assert reason == params.SOURCE_ERROR_NOTE


def test_missing_soil_means_the_stand_in_capacity(client, reports_db, optional_sources):
    down = recorded_soil_source(category_status=503, texture_status=503)
    optional_sources.current = replace(optional_sources.recorded(), soil=down)
    status, report, outcomes = run(client, reports_db)
    reason = check_missing("soil", status, report, outcomes)
    assert reason.startswith("Nie udało się pobrać danych o glebie.")
    assert "mapa kategorii gleb nie odpowiedziała" in reason
    assert "globalna mapa gleb nie odpowiedziała" in reason
    capacity = next(e.values for e in report.trace if e.rule_id == "root_zone.capacity")
    assert capacity["capacity_source"] == "fallback"
    assert capacity["total_available_water_mm"] == 150
    assert "przyjęto przeciętną zdolność gleby" in report.current_status.confidence.why
    texts = [limitation.text for limitation in report.limitations]
    assert NO_SOIL_TEXT in texts
    # The limitation of the category map that was never read is not listed.
    assert not any("IUNG-PIB" in text for text in texts)


def soil_of(report: Report, outcomes: dict) -> tuple[dict, list[str], object]:
    capacity = next(e.values for e in report.trace if e.rule_id == "root_zone.capacity")
    source = next(source for source in report.sources if source.topic == "soil")
    return capacity, [limitation.text for limitation in report.limitations], source


def test_parcel_without_a_category_uses_the_texture_estimate(
    client, reports_db, optional_sources
):
    forest = recorded_soil_source(category=point_answer("forest"))
    optional_sources.current = replace(optional_sources.recorded(), soil=forest)
    _, report, outcomes = run(client, reports_db)
    capacity, texts, source = soil_of(report, outcomes)
    assert capacity["capacity_source"] == "texture_estimate"
    # Estimated category II: 149 mm per metre over the 100 cm root zone.
    assert (capacity["soil_category"], capacity["total_available_water_mm"]) == ("II", 149)
    assert (source.name, source.chain_step, source.missing) == ("ISRIC SoilGrids 2.0", 2, False)
    assert source.license.startswith("CC BY 4.0")
    assert outcomes["soil"].chain_step == 2 and "użyto zamiennika" in outcomes["soil"].message
    assert texts.count(NO_CATEGORY_TEXT) == 1
    assert not any("mniej dokładnego zamiennika" in text for text in texts)
    assert "oszacowano z globalnej mapy gleb" in report.current_status.confidence.why


def test_category_map_down_uses_the_texture_estimate(client, reports_db, optional_sources):
    down = recorded_soil_source(category_status=503)
    optional_sources.current = replace(optional_sources.recorded(), soil=down)
    _, report, outcomes = run(client, reports_db)
    capacity, texts, source = soil_of(report, outcomes)
    assert capacity["capacity_source"] == "texture_estimate"
    assert source.chain_step == 2
    assert any(text.startswith("Nie udało się odczytać kategorii gleby") for text in texts)


def test_organic_soil_is_not_assessed_from_texture(client, reports_db, optional_sources):
    organic = recorded_soil_source(category=point_answer("organic"))
    optional_sources.current = replace(optional_sources.recorded(), soil=organic)
    _, report, outcomes = run(client, reports_db)
    capacity, texts, source = soil_of(report, outcomes)
    assert (capacity["capacity_source"], capacity["total_available_water_mm"]) == ("fallback", 150)
    assert (source.chain_step, source.missing) == (1, False)
    assert ORGANIC_TEXT in texts and NO_SOIL_TEXT not in texts
    assert "glebę organiczną" in report.current_status.confidence.why


def test_terrain_catalogue_down(client, reports_db, optional_sources, tmp_path):
    optional_sources.current = replace(
        optional_sources.recorded(), terrain=recorded_terrain_source(tmp_path, status=503)
    )
    reason = check_missing("terrain", *run(client, reports_db))
    assert reason.startswith("Nie udało się pobrać danych o ukształtowaniu terenu.")
    assert "katalog modelu wysokości nie odpowiedział" in reason


def test_satellite_catalogue_down(client, reports_db, optional_sources):
    down = SatelliteSource(
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        providers=[EARTH_SEARCH],
    )
    optional_sources.current = replace(optional_sources.recorded(), satellite=down)
    reason = check_missing("satellite", *run(client, reports_db))
    assert "Katalog zdjęć satelitarnych nie odpowiedział" in reason
    assert "21.05.2023–20.06.2023" in reason


def test_drought_files_absent(client, reports_db, optional_sources, tmp_path):
    empty = DroughtBackgroundSource(tmp_path / "no-such-directory")
    optional_sources.current = replace(optional_sources.recorded(), drought_background=empty)
    reason = check_missing("drought_background", *run(client, reports_db))
    assert reason == "Brak plików wskaźnika CDI na serwerze."


def test_drought_directory_comes_from_the_environment(
    client, reports_db, optional_sources, tmp_path, monkeypatch
):
    monkeypatch.setenv("EDO_DATA_PATH", str(tmp_path / "unset"))
    optional_sources.current = replace(
        optional_sources.recorded(), drought_background=DroughtBackgroundSource()
    )
    _, report, outcomes = run(client, reports_db)
    assert outcomes["drought_background"].message == "Brak plików wskaźnika CDI na serwerze."
    assert next(s for s in report.sources if s.topic == "drought_background").missing
