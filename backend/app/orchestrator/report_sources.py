"""Report parts that describe the data: the source list and the limitations."""

from app.contracts.report import Limitation, ReportSource
from app.contracts.source_data import SourceData, SourceOutcome, SourceTopic
from app.engine.root_zone import RootZone

# Licence and access mode per topic, as documented in the README source table.
# A topic gets its entry when its source is connected to the analysis.
_SOURCE_TERMS: dict[SourceTopic, tuple[str, str]] = {
    "parcel": ("ULDK GUGiK", "bezpłatnie, bez rejestracji; wymagane podanie źródła"),
    "weather": (
        "Open-Meteo, archiwum pogodowe",
        "CC BY 4.0, wymagane podanie źródła; bezpłatny dostęp tylko do zastosowań niekomercyjnych",
    ),
}
_UNKNOWN_TERMS = ("źródło nieokreślone", "nie podano")

# How the optional parts of the source data are named in a limitation.
_OPTIONAL_TOPICS: dict[SourceTopic, str] = {
    "terrain": "ukształtowanie terenu",
    "hydro": "cieki, rowy i zbiorniki",
    "satellite": "odczyty satelitarne",
    "drought_background": "niezależny wskaźnik suszy",
}


def report_source(outcome: SourceOutcome) -> ReportSource:
    name, licence = _SOURCE_TERMS.get(outcome.topic, _UNKNOWN_TERMS)
    return ReportSource(
        topic=outcome.topic,
        name=outcome.source_name or name,
        license=licence,
        mode="na żywo",
        data_date=outcome.data_date,
        fetched_at=outcome.fetched_at,
        # The contract needs a chain step even for a missing source; `missing` tells.
        chain_step=outcome.chain_step or 1,
        missing=not outcome.ok,
    )


def report_sources(source_data: SourceData) -> list[ReportSource]:
    return [report_source(outcome) for outcome in source_data.outcomes]


def soil_limitation(zone: RootZone) -> Limitation | None:
    """Says that the water capacity is a stand-in value, when it is."""
    if zone.capacity_source != "fallback":
        return None
    return Limitation(
        text=(
            "Brak danych o glebie działki: pojemność wodną gleby przyjęto zastępczo "
            f"({zone.available_water_mm_per_m:.0f} mm wody dostępnej na metr głębokości). "
            "Oba werdykty zależą od tej wartości."
        ),
        affects="all",
        permanent=False,
    )


def absent_data_limitation(source_data: SourceData) -> Limitation | None:
    """Names the optional data the analysis ran without."""
    absent = [
        label for topic, label in _OPTIONAL_TOPICS.items() if getattr(source_data, topic) is None
    ]
    if not absent:
        return None
    return Limitation(
        text=f"Analiza nie korzysta z danych: {', '.join(absent)}.",
        affects="all",
        permanent=False,
    )
