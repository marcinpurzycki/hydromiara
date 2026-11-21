"""What one comparison of the consistency check returns, and shared wording."""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.contracts.common import Scalar
from app.contracts.report import Limitation
from app.contracts.verdicts import ConsistencyItem
from app.engine.findings import Finding

# Result of one comparison; None when nothing was compared.
PartResult = Literal["zgodne", "rozbieżne"]

NO_DATA = "brak danych"
NO_EFFECT = "Nie wpływa na wynik Sprawdzenia zgodności."


@dataclass(frozen=True)
class Comparison:
    """One independent source set against the verdict, or only described."""

    items: tuple[ConsistencyItem, ...]
    result: PartResult | None
    # Full sentences about this source for the sentence of the check.
    clause: str
    # A gap in the comparison data that no other limitation names.
    finding: Finding | None = None
    # True when `finding` says more precisely what the general limitation
    # about the missing data category would say.
    replaces_missing: bool = False
    # Values behind the comparison, for the decision trace.
    facts: dict[str, Scalar] = field(default_factory=dict)


def pl(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def period(first: date, last: date) -> str:
    return f"{pl(first)}–{pl(last)}"


def gap_finding(text: str, reason: str) -> Finding:
    """A limitation of the current water status: its comparison could not be made."""
    return Finding(
        limitation=Limitation(text=text, affects="current", permanent=False), reason=reason
    )
