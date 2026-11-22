"""Result of checking one deficit cause, before it is written into the Report.

A cause has three states. The contract has only `found: bool`, so "no data"
is written as `found = false` with `indicator.value = null` and a finding
that says the cause could not be assessed; "not found" always has a value.

The values kept here are the ones shown to the user (already rounded), and
the decision is made on them, so a shown value never contradicts its result.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.contracts.causes import Cause, CauseId, Fact, Indicator, Recommendation
from app.contracts.common import Scalar
from app.contracts.report import TraceEntry

CauseState = Literal["found", "not_found", "no_data"]

# Wording of the three states in the decision trace.
STATE_RESULTS: dict[CauseState, str] = {
    "found": "stwierdzono",
    "not_found": "nie stwierdzono",
    "no_data": "brak danych",
}

# Fixed order of the causes; ties in the report order fall back to it.
CAUSE_ORDER: tuple[CauseId, ...] = ("precipitation", "soil", "runoff", "crop_demand")


@dataclass(frozen=True)
class SourceNames:
    """How the data sources are named next to the facts of a cause."""

    weather: str = "dane pogodowe"
    soil: str = "dane o glebie"
    terrain: str = "dane o ukształtowaniu terenu"


def pl_number(value: float, digits: int = 0) -> str:
    """A number as written in Polish: decimal comma, fixed number of digits."""
    return f"{value:.{digits}f}".replace(".", ",")


@dataclass(frozen=True)
class CauseResult:
    id: CauseId
    state: CauseState
    finding: str
    indicator_name: str
    unit: str
    # Value for the parcel as shown; None when there are no data to assess.
    value: float | None
    threshold: float
    # The rule in words, for the decision trace.
    condition: str
    facts: tuple[Fact, ...] = ()
    trace_values: Mapping[str, Scalar] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return self.state == "found"

    @property
    def strength(self) -> float:
        """How far a found cause lies beyond its threshold, relative to it.

        PROVISIONAL: no source for comparing causes measured in different
        units; the relative distance from the threshold is a working rule
        used only to order the found causes.
        """
        if not self.found or self.value is None:
            return 0.0
        return abs(self.value - self.threshold) / self.threshold

    def to_contract(self, recommendations: Sequence[Recommendation] = ()) -> Cause:
        """The cause as a Report section; recommendations are attached by the caller."""
        return Cause(
            id=self.id,
            found=self.found,
            finding=self.finding,
            indicator=Indicator(
                name=self.indicator_name,
                value=self.value,
                unit=self.unit,
                threshold=self.threshold,
            ),
            facts=list(self.facts),
            recommendations=list(recommendations),
        )

    def trace_entry(self) -> TraceEntry:
        return TraceEntry(
            rule_id=f"cause.{self.id}",
            condition=self.condition,
            values={**self.trace_values, "threshold": self.threshold},
            result=STATE_RESULTS[self.state],
        )
