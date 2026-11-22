"""Limitations and confidence in the Report of a whole analysis run."""

import json
from datetime import date

import pytest

from app.contracts.report import Limitation, Report
from app.contracts.source_data import SatelliteData, SatelliteScene
from app.engine.limitations import PERMANENT_LIMITATIONS
from app.main import app
from app.orchestrator.sources import (
    AnalysisSources,
    OptionalSources,
    SourceFetch,
    SourceSpec,
    default_specs,
    get_analysis_sources,
)
from app.sources.weather import WeatherSource
from tests.analysis_helpers import start, wait_finished
from tests.limitation_helpers import complete_source_data, outcome

WINDOW = Limitation(
    text="W okresie 21.05.2023–20.06.2023 żadna scena satelitarna nie jest czysta.",
    affects="current",
    permanent=False,
)
SERVICE_DOWN = Limitation(
    text="Usługa glebowa nie odpowiedziała.", affects="all", permanent=False
)


@pytest.fixture
def use_fetches(parcel_source, weather):
    """Connect extra sources of new analyses by topic; restored after the test."""

    def install(fetches: dict) -> None:
        specs = tuple(
            SourceSpec(spec.topic, spec.status_id, 1.0, fetch=fetches[spec.topic])
            if spec.topic in fetches
            else spec
            for spec in default_specs(WeatherSource(transport=weather))
        )
        sources = AnalysisSources(parcels=parcel_source, specs=specs)
        app.dependency_overrides[get_analysis_sources] = lambda: sources

    yield install
    app.dependency_overrides.pop(get_analysis_sources, None)


def finished_report(client) -> Report:
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    return Report.model_validate(client.get(f"/api/reports/{report_id}").json())


def texts(report: Report) -> list[str]:
    return [limitation.text for limitation in report.limitations]


def test_report_of_an_analysis_has_confidence_and_the_permanent_limitations(client):
    report = finished_report(client)
    assert tuple(report.limitations[-len(PERMANENT_LIMITATIONS):]) == PERMANENT_LIMITATIONS
    assert len(set(texts(report))) == len(report.limitations)
    # Every source answered: nothing of this analysis concerns the current status.
    assert report.current_status.confidence.level == "wysoka"
    # The recorded catalogue has no scenes for the five earlier years: one limitation.
    multiyear = report.multiyear_susceptibility.confidence
    assert multiyear.level == "średnia"
    assert multiyear.why.startswith("Pewność oceny obniża: Z tego samego okresu roku nie ma")
    assert not any("Pewności oceny" in text for text in texts(report))


def test_without_the_optional_sources_both_confidences_are_low(client, optional_sources):
    optional_sources.current = OptionalSources()
    report = finished_report(client)
    for verdict in (report.current_status, report.multiyear_susceptibility):
        assert verdict.confidence.level == "niska"
        assert verdict.confidence.why.startswith("Pewność oceny obniżają: ")
        assert "przyjęto przeciętną zdolność gleby" in verdict.confidence.why


def test_weather_ending_before_the_date_is_named_once(client, weather):
    payload = json.loads(weather.payload)
    for position, day in enumerate(payload["daily"]["time"]):
        if date(2023, 6, 18) <= date.fromisoformat(day):
            for series in ("precipitation_sum", "et0_fao_evapotranspiration"):
                payload["daily"][series][position] = None
    weather.payload = json.dumps(payload)
    report = finished_report(client)
    gaps = [limitation for limitation in report.limitations if "kończą się" in limitation.text]
    assert len(gaps) == 1 and gaps[0].affects == "current"
    assert "17.06.2023, czyli 3 dni przed Datą analizy" in gaps[0].text
    assert "kończą się 3 dni przed Datą analizy" in report.current_status.confidence.why
    assert "kończą się" not in report.multiyear_susceptibility.confidence.why
    assert report.current_status.details["state_date"] == "2023-06-17"


def test_source_limitations_count_only_when_the_source_gave_data(client, use_fetches):
    async def satellite(context) -> SourceFetch:
        scene = SatelliteScene(date=date(2022, 6, 1), clear_share_pct=95, ndvi=0.5, ndmi=0.1)
        data = SatelliteData(scenes=[scene])
        return SourceFetch(data=data, outcome=outcome("satellite", 2), limitations=[WINDOW])

    async def soil(context) -> SourceFetch:
        return SourceFetch(data=None, outcome=outcome("soil", None), limitations=[SERVICE_DOWN])

    use_fetches({"satellite": satellite, "soil": soil})
    report = finished_report(client)
    assert WINDOW in report.limitations and SERVICE_DOWN not in report.limitations
    assert not any(text.startswith("Brak odczytów satelitarnych") for text in texts(report))
    assert not any("zamiennika" in text for text in texts(report))
    assert sum(text.startswith("Nie udało się pobrać danych o glebie") for text in texts(report)) == 1
    assert "żadna scena satelitarna" in report.current_status.confidence.why
    assert "żadna scena satelitarna" not in report.multiyear_susceptibility.confidence.why
    satellite_source = next(source for source in report.sources if source.topic == "satellite")
    assert satellite_source.chain_step == 2 and not satellite_source.missing


def test_terrain_from_a_substitute_is_named_at_the_recommendations(client, use_fetches):
    async def terrain(context) -> SourceFetch:
        data = complete_source_data().terrain
        return SourceFetch(data=data, outcome=outcome("terrain", 2, "Copernicus DEM GLO-30"))

    use_fetches({"terrain": terrain})
    report = finished_report(client)
    (named,) = [limitation for limitation in report.limitations if "zamiennika" in limitation.text]
    assert named.affects == "recommendations" and "Copernicus DEM GLO-30" in named.text
    assert "zamiennika" not in report.current_status.confidence.why
