"""All limitations of one Report, in a fixed order and without repeats.

Sources of a limitation:
- the permanent ones, present in every Report (`permanent_limitations`);
- what the water assessment shows about its own inputs: a stand-in water
  capacity, a soil profile covering part of the depth, and the gaps of the
  weather series (`weather_limitations`);
- how the source data were obtained: a missing data category, data from a
  less accurate substitute;
- the consistency check ending as divergent;
- limitations the source adapters returned next to their data.

Pure: the same inputs always give the same list. Order: limitations of this
analysis first, the permanent ones last.
"""

from collections.abc import Collection, Iterable, Sequence
from typing import Literal

from app.contracts.report import Limitation
from app.contracts.source_data import SourceData, SourceTopic
from app.engine.assessment import WaterAssessment
from app.engine.findings import POINTS_DIVERGENT, POINTS_STAND_IN, Finding, plain
from app.engine.permanent_limitations import PERMANENT_LIMITATIONS, SIMULATION_LIMITATIONS
from app.engine.source_limitations import (
    Affects,
    missing_source_findings,
    step_down_findings,
)
from app.engine.weather_limitations import weather_findings

__all__ = [
    "PERMANENT_LIMITATIONS",
    "SIMULATION_LIMITATIONS",
    "ConsistencyResult",
    "consistency_findings",
    "limitations_of",
    "report_findings",
    "soil_findings",
    "weather_findings",
]

ConsistencyResult = Literal["zgodne", "rozbieżne", "brak danych"]


def _finding(text: str, affects: Affects, reason: str, points: int | None = None) -> Finding:
    limitation = Limitation(text=text, affects=affects, permanent=False)
    if points is None:
        return Finding(limitation=limitation, reason=reason)
    return Finding(limitation=limitation, points=points, reason=reason)


def soil_findings(assessment: WaterAssessment) -> list[Finding]:
    """What the root zone used by the balance says about the soil data."""
    zone = assessment.root_zone
    if zone.capacity_source == "fallback":
        return [
            _finding(
                "Brak danych o glebie Działki: pojemność wodną gleby przyjęto zastępczo "
                f"({zone.available_water_mm_per_m:.0f} mm wody dostępnej na metr "
                "głębokości). Od tej wartości zależą oba werdykty: Bieżąca sytuacja wodna "
                "i Podatność wieloletnia.",
                "all",
                "pojemność wodną gleby przyjęto zastępczo, bez danych o glebie Działki",
                POINTS_STAND_IN,
            )
        ]
    if zone.capacity_source == "partial_soil_profile":
        return [
            _finding(
                f"Dane o glebie obejmują {zone.covered_cm:.0f} cm z {zone.depth_cm:.0f} cm "
                "głębokości przyjętej w bilansie wodnym; dla pozostałej części przyjęto taką "
                "samą pojemność wodną. Wpływa to na oba werdykty.",
                "all",
                "dane o glebie obejmują tylko część głębokości przyjętej w bilansie wodnym",
            )
        ]
    return []


def consistency_findings(
    result: ConsistencyResult | None, affects: Affects = "current"
) -> list[Finding]:
    """The divergent consistency check as a limitation of the verdict it compared.

    The other results add nothing: missing comparison data are already named
    by the limitations of their sources.
    """
    if result != "rozbieżne":
        return []
    return [
        _finding(
            "Sprawdzenie zgodności dało wynik „rozbieżne”: werdykt różni się od "
            "niezależnego wskaźnika suszy lub od odczytu satelitarnego dla tego samego "
            "okresu. Szczegóły są w części Sprawdzenie zgodności.",
            affects,
            "Sprawdzenie zgodności dało wynik „rozbieżne”",
            POINTS_DIVERGENT,
        )
    ]


def _unique(findings: Iterable[Finding]) -> list[Finding]:
    seen: set[str] = set()
    kept = []
    for finding in findings:
        if finding.limitation.text not in seen:
            seen.add(finding.limitation.text)
            kept.append(finding)
    return kept


def report_findings(
    source_data: SourceData,
    assessment: WaterAssessment,
    *,
    source_limitations: Sequence[Limitation] = (),
    consistency: ConsistencyResult | None = None,
    consistency_affects: Affects = "current",
    consistency_gaps: Sequence[Finding] = (),
    replaced_missing: Collection[SourceTopic] = (),
    first: Sequence[Limitation] = (),
    last: Sequence[Limitation] = (),
) -> tuple[Finding, ...]:
    """Every limitation of the Report with its weight for the confidence.

    `consistency` is the result of the consistency check, when it was made;
    `consistency_gaps` are the gaps in its comparison data, which replace the
    general limitation of the missing categories in `replaced_missing`.
    `first` and `last` are limitations of the caller placed before and after
    those found here. A text is kept once, at its first position.
    """
    found = _unique(
        [
            *(plain(limitation) for limitation in first),
            *consistency_findings(consistency, consistency_affects),
            *consistency_gaps,
            *soil_findings(assessment),
            *weather_findings(assessment, source_data.outcomes),
            *step_down_findings(source_data.outcomes),
            *missing_source_findings(source_data, replaced_missing),
            *(plain(limitation) for limitation in source_limitations),
            *(plain(limitation) for limitation in last),
            *(plain(limitation) for limitation in PERMANENT_LIMITATIONS),
        ]
    )
    # Stable: limitations of this analysis first, the permanent ones last.
    return tuple(sorted(found, key=lambda finding: finding.limitation.permanent))


def limitations_of(findings: Iterable[Finding]) -> list[Limitation]:
    """The list for the Report."""
    return [finding.limitation for finding in findings]
