"""Helpers for the confidence and limitation tests: source data with every category."""

from datetime import date

from app.contracts.common import GeoJsonGeometry
from app.contracts.report import Limitation
from app.contracts.source_data import (
    CdiDekad,
    DroughtBackground,
    HydroData,
    HydroObject,
    SatelliteData,
    SatelliteScene,
    SourceData,
    SourceOutcome,
    TerrainData,
)
from app.engine.assessment import WaterAssessment, assess_water
from app.engine.confidence import VerdictConfidences, verdict_confidences
from app.engine.findings import Finding
from app.engine.limitations import report_findings
from tests.analysis_helpers import ANALYSIS_DATE, NOW
from tests.engine_helpers import WHEAT, recorded_soil, recorded_weather, source_data

TOPIC_NAMES = {
    "parcel": "ULDK GUGiK",
    "weather": "Open-Meteo",
    "soil": "SoilGrids",
    "terrain": "GUGiK NMT 1 m",
    "hydro": "BDOT10k",
    "satellite": "Sentinel-2 L2A",
    "drought_background": "EDO CDI",
}
NO_CROP_SENTENCE = "Dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany."


def outcome(topic: str, step: int | None = 1, name: str | None = None) -> SourceOutcome:
    return SourceOutcome(
        topic=topic,
        source_name=(name or TOPIC_NAMES[topic]) if step else None,
        chain_step=step,
        ok=step is not None,
        duration_s=0.3,
        data_date=None,
        fetched_at=NOW,
    )


def complete_source_data(days=None) -> SourceData:
    """Recorded weather and soil plus small stand-ins for every other category."""
    data = source_data(recorded_weather() if days is None else days, recorded_soil())
    line = GeoJsonGeometry(type="LineString", coordinates=[[18.2, 52.75], [18.21, 52.75]])
    return data.model_copy(
        update={
            "terrain": TerrainData(
                resolution_m=1.0,
                crs="EPSG:2180",
                transform=(1.0, 0.0, 0.0, 0.0, -1.0, 0.0),
                elevations_m=[[100.0, 101.0]],
            ),
            "hydro": HydroData(objects=[HydroObject(kind="ditch", name=None, geometry=line)]),
            "satellite": SatelliteData(
                scenes=[
                    SatelliteScene(date=date(2023, 6, 10), clear_share_pct=97, ndvi=0.6, ndmi=0.2)
                ]
            ),
            "drought_background": DroughtBackground(
                dekads=[CdiDekad(date=date(2023, 6, 11), cdi_class=1)]
            ),
            "outcomes": [outcome(topic) for topic in TOPIC_NAMES],
        }
    )


def without(data: SourceData, topic: str) -> SourceData:
    outcomes = [outcome(topic, None) if o.topic == topic else o for o in data.outcomes]
    return data.model_copy(update={topic: None, "outcomes": outcomes})


def with_step(data: SourceData, topic: str, step: int, name: str) -> SourceData:
    outcomes = [outcome(topic, step, name) if o.topic == topic else o for o in data.outcomes]
    return data.model_copy(update={"outcomes": outcomes})


def limitation(
    affects: str, text: str = "Brak przykładowy.", permanent: bool = False
) -> Limitation:
    return Limitation(text=text, affects=affects, permanent=permanent)


def judge(
    data: SourceData, crop=WHEAT, analysis_date: date = ANALYSIS_DATE, **options
) -> tuple[tuple[Finding, ...], VerdictConfidences, WaterAssessment]:
    """Findings and both confidences the way the report builder derives them."""
    assessment = assess_water(data, crop, analysis_date)
    findings = report_findings(data, assessment, **options)
    no_crop = None if crop.growth is not None else NO_CROP_SENTENCE
    confidences = verdict_confidences(
        findings, current_not_assessed=no_crop, multiyear_not_assessed=no_crop
    )
    return findings, confidences, assessment


def own_texts(findings) -> list[str]:
    """Texts of the limitations of this analysis, without the permanent ones."""
    return [f.limitation.text for f in findings if not f.limitation.permanent]
