"""Consistency check: the verdict of the Report against two independent sources.

The current water status is set against the drought indicator of the same
dekad (`consistency_cdi`) and shown next to the satellite reading for the same
period (`consistency_satellite`). The multi-year susceptibility is not
compared: neither source is read for the whole multi-year window.

Overall result from the results of the comparisons:
- any comparison ends as divergent -> "rozbieżne";
- otherwise any comparison ends as consistent -> "zgodne" (the sentence says
  what the other source contributed);
- otherwise -> "brak danych".
A verdict without a deficit level (the field without a crop, no weather)
cannot be compared: the result is "brak danych" with the reason, and the
independent data are only described.

The rules of both comparisons are working values in `consistency_params`.
Pure and deterministic: no network, clock or state; nothing dated after the
analysis date is read.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import in_season
from app.contracts.report import TraceEntry
from app.contracts.source_data import SourceData, SourceTopic
from app.contracts.verdicts import ConsistencyCheck
from app.engine.assessment import WaterAssessment
from app.engine.consistency_cdi import compare_cdi
from app.engine.consistency_params import DEFAULT_CONSISTENCY_PARAMS, ConsistencyParams
from app.engine.consistency_parts import Comparison, PartResult
from app.engine.consistency_satellite import SeasonState, describe_satellite
from app.engine.findings import Finding
from app.engine.limitations import ConsistencyResult
from app.engine.source_limitations import Affects

RULE_ID = "consistency_check.result"

_HEADS: dict[ConsistencyResult, str] = {
    "zgodne": "Zgodne.",
    "rozbieżne": "Rozbieżne.",
    "brak danych": "Brak danych.",
}
_NOT_ASSESSED = {
    "no_crop": "dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany",
    "no_weather": "bez danych pogodowych Bieżąca sytuacja wodna nie ma Stopnia niedoboru",
}


@dataclass(frozen=True)
class ConsistencyOutcome:
    """The consistency check of a Report and what it means for the rest of it."""

    check: ConsistencyCheck
    # The verdict whose confidence a divergent result lowers.
    affects: Affects
    # Gaps in the comparison data that no other limitation names.
    findings: tuple[Finding, ...]
    # Data categories whose general "missing" limitation is replaced by a
    # more precise one in `findings`.
    replaces_missing: frozenset[SourceTopic]
    trace: TraceEntry

    @property
    def result(self) -> ConsistencyResult:
        return self.check.result


def combine(results: Iterable[PartResult | None]) -> ConsistencyResult:
    """Overall result of the check from the results of its comparisons."""
    found = set(results)
    if "rozbieżne" in found:
        return "rozbieżne"
    if "zgodne" in found:
        return "zgodne"
    return "brak danych"


def season_state(crop: CatalogCrop, analysis_date: date) -> SeasonState:
    if crop.season is None:
        return "no_crop"
    return "in_season" if in_season(crop, analysis_date) else "out_of_season"


def _classes(params: ConsistencyParams, signal: str) -> str:
    chosen = sorted(c for c, s in params.cdi_class_signals.items() if s == signal)
    return ", ".join(str(cdi_class) for cdi_class in chosen) or "brak"


def _trace(
    params: ConsistencyParams,
    level: int | None,
    cdi: Comparison,
    satellite: Comparison,
    result: ConsistencyResult,
) -> TraceEntry:
    return TraceEntry(
        rule_id=RULE_ID,
        condition=(
            "zgodne, gdy Stopień niedoboru Bieżącej sytuacji wodnej jest co najmniej "
            f"{params.deficit_from_level} i klasa CDI wskazuje suszę "
            f"({_classes(params, 'drought')}) albo jest niższy i klasa CDI jej nie wskazuje "
            f"({_classes(params, 'no_drought')}); klasy przejściowe "
            f"({_classes(params, 'transitional')}) nie są zestawiane; dekada CDI to ostatnia "
            "zakończona nie później niż Data analizy; odczyt satelitarny jest opisowy"
        ),
        values={
            "deficit_level": level,
            **cdi.facts,
            **satellite.facts,
            "satellite_result": satellite.result,
        },
        result=result,
    )


def check_consistency(
    source_data: SourceData,
    assessment: WaterAssessment,
    crop: CatalogCrop,
    analysis_date: date,
    params: ConsistencyParams = DEFAULT_CONSISTENCY_PARAMS,
) -> ConsistencyOutcome:
    """The consistency check for the current water status on the analysis date."""
    verdict = assessment.current_status
    state = season_state(crop, analysis_date)
    cdi = compare_cdi(
        source_data.drought_background,
        verdict,
        analysis_date,
        out_of_season=state == "out_of_season",
        params=params,
    )
    satellite = describe_satellite(
        source_data.satellite, analysis_date, season_state=state, params=params
    )
    if verdict.assessed:
        result = combine((cdi.result, satellite.result))
        sentence = f"{_HEADS[result]} {cdi.clause} {satellite.clause}"
    else:
        result = "brak danych"
        sentence = (
            f"{_HEADS[result]} Sprawdzenia zgodności nie wykonano: "
            f"{_NOT_ASSESSED[verdict.not_assessed_reason]}, więc nie ma werdyktu do "
            "zestawienia. Pozycje Sprawdzenia zgodności podają niezależne dane tylko opisowo."
        )
    parts = (cdi, satellite)
    replaced: set[SourceTopic] = set()
    if cdi.replaces_missing:
        replaced.add("drought_background")
    return ConsistencyOutcome(
        check=ConsistencyCheck(
            result=result,
            sentence=sentence,
            items=[item for part in parts for item in part.items],
        ),
        affects="current",
        findings=tuple(part.finding for part in parts if part.finding is not None),
        replaces_missing=frozenset(replaced),
        trace=_trace(params, verdict.deficit_level, cdi, satellite, result),
    )
