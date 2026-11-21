"""Report part that describes the data: the source list."""

from app.contracts.report import ReportSource
from app.contracts.source_data import SourceData, SourceOutcome, SourceTopic

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
