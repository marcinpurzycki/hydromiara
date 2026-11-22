"""Deficit causes of one Report: when they are determined, which are found, in what order.

Causes are determined only when at least one of the two verdicts shows a
deficit (level 1 or higher). Otherwise the list is empty and the outcome
carries a sentence that says so:
- no verdict shows a deficit: no causes and therefore no recommendations;
- no verdict could be assessed (the field without a crop, or no weather):
  causes are not determined and no agronomic rule replaces the verdicts.

When determined, all four causes are checked and each gets one of three
states (found, not found, no data), an indicator with its threshold and the
value for the parcel, the facts behind it and one entry of the decision trace.
Found causes come first, the strongest first; then those not found; then
those without data.

Recommendations are not created here. The rule engine receives the
`CausesOutcome`, reads `results` and hands the recommendations of each cause
to `CausesOutcome.causes`.

Pure: the same inputs always give the same outcome.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.catalog.crop_model import CatalogCrop
from app.contracts.causes import Cause, CauseId, Recommendation
from app.contracts.report import TraceEntry
from app.engine.assessment import WaterAssessment
from app.engine.cause_model import CAUSE_ORDER, CauseResult, SourceNames
from app.engine.cause_params import DEFAULT_CAUSE_PARAMS, CauseParams
from app.engine.cause_site_checks import runoff_cause, soil_cause
from app.engine.cause_weather_checks import crop_demand_cause, precipitation_cause
from app.engine.terrain_analysis import TerrainAnalysis

CausesStatus = Literal["determined", "no_deficit", "not_assessed"]

NO_DEFICIT_SENTENCE = (
    "Na tej Działce nie stwierdzono niedoboru wody dla tej Uprawy, więc nie przedstawiamy "
    "Rekomendacji."
)
ONE_VERDICT_NOTE = " Oceniono tylko jeden z dwóch werdyktów; drugi nie ma Stopnia niedoboru."
NOT_ASSESSED_SENTENCE = (
    "Przyczyn niedoboru nie wyznaczono, bo żaden z dwóch werdyktów nie ma Stopnia niedoboru. "
    "Raport nie zawiera więc Rekomendacji."
)
_GATE_CONDITION = (
    "Przyczyny niedoboru są wyznaczane, gdy co najmniej jeden werdykt ma Stopień niedoboru "
    "co najmniej 1 (lekki niedobór)"
)
_GATE_RESULTS: dict[CausesStatus, str] = {
    "determined": "wyznaczono Przyczyny niedoboru",
    "no_deficit": "nie wyznaczano: żaden werdykt nie wskazuje niedoboru",
    "not_assessed": "nie wyznaczano: żaden werdykt nie ma Stopnia niedoboru",
}
_STATE_RANK = {"found": 0, "not_found": 1, "no_data": 2}


@dataclass(frozen=True)
class CausesOutcome:
    status: CausesStatus
    # Sentence for the Report when the causes were not determined.
    statement: str | None
    # Checked causes in report order; empty unless the status is "determined".
    results: tuple[CauseResult, ...]
    gate: TraceEntry

    @property
    def found(self) -> tuple[CauseResult, ...]:
        return tuple(result for result in self.results if result.found)

    def causes(
        self, recommendations: Mapping[CauseId, Sequence[Recommendation]] | None = None
    ) -> list[Cause]:
        """Report sections; `recommendations` maps a cause to its recommendations."""
        given = recommendations or {}
        return [result.to_contract(given.get(result.id, ())) for result in self.results]

    def trace(self) -> list[TraceEntry]:
        """The gate and one entry per checked cause, in the fixed cause order."""
        by_id = {result.id: result for result in self.results}
        return [self.gate, *(by_id[cause].trace_entry() for cause in CAUSE_ORDER if cause in by_id)]


def causes_status(assessment: WaterAssessment) -> CausesStatus:
    levels = [
        verdict.deficit_level
        for verdict in (assessment.current_status, assessment.multiyear_susceptibility)
        if verdict.assessed
    ]
    if not levels:
        return "not_assessed"
    return "determined" if max(levels) >= 1 else "no_deficit"


def _statement(status: CausesStatus, assessment: WaterAssessment) -> str | None:
    if status == "determined":
        return None
    if status == "not_assessed":
        return NOT_ASSESSED_SENTENCE
    both = assessment.current_status.assessed and assessment.multiyear_susceptibility.assessed
    return NO_DEFICIT_SENTENCE + ("" if both else ONE_VERDICT_NOTE)


def ordered(results: Sequence[CauseResult]) -> tuple[CauseResult, ...]:
    """Found causes first and the strongest first; then not found; then no data."""
    return tuple(
        sorted(
            results,
            key=lambda result: (
                _STATE_RANK[result.state],
                -result.strength,
                CAUSE_ORDER.index(result.id),
            ),
        )
    )


def deficit_causes(
    assessment: WaterAssessment,
    crop: CatalogCrop,
    terrain: TerrainAnalysis | None,
    params: CauseParams = DEFAULT_CAUSE_PARAMS,
    sources: SourceNames = SourceNames(),
) -> CausesOutcome:
    """The deficit causes for the assessment; `terrain` is None without terrain data."""
    current, multiyear = assessment.current_status, assessment.multiyear_susceptibility
    status = causes_status(assessment)
    gate = TraceEntry(
        rule_id="causes.gate",
        condition=_GATE_CONDITION,
        values={
            "current_deficit_level": current.deficit_level,
            "multiyear_deficit_level": multiyear.deficit_level,
        },
        result=_GATE_RESULTS[status],
    )
    if status != "determined":
        return CausesOutcome(
            status=status, statement=_statement(status, assessment), results=(), gate=gate
        )
    results = (
        precipitation_cause(assessment, params, sources),
        soil_cause(assessment, params, sources),
        runoff_cause(terrain, params, sources),
        crop_demand_cause(assessment, crop, params, sources),
    )
    return CausesOutcome(status=status, statement=None, results=ordered(results), gate=gate)
