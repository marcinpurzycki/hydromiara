"""A report limitation together with what it means for the confidence of a verdict.

The Report shows plain limitations. Inside the engine each of them also carries
its weight for the confidence rule and a short wording used in the
justification of the confidence level.

No rule for the confidence is given by a scientific source, so every number
here is a working value kept in one place.
"""

from dataclasses import dataclass
from typing import Literal

from app.contracts.report import Limitation

# The two verdicts of the Report; each has its own confidence.
VerdictKey = Literal["current", "multiyear"]

# PROVISIONAL: no source; weight of an ordinary limitation in the confidence rule.
POINTS_DEFAULT = 1
# PROVISIONAL: no source; weight of a limitation about a stand-in for data the
# verdict is computed from (the water capacity without soil data).
POINTS_STAND_IN = 2
# PROVISIONAL: no source; weight of the consistency check ending as divergent.
POINTS_DIVERGENT = 2
# PROVISIONAL: no source; from this many points the confidence is medium.
POINTS_FOR_MEDIUM = 1
# PROVISIONAL: no source; from this many points the confidence is low.
POINTS_FOR_LOW = 3


@dataclass(frozen=True)
class ConfidenceParams:
    """Thresholds of the confidence rule; replace to try other values."""

    points_for_medium: int = POINTS_FOR_MEDIUM
    points_for_low: int = POINTS_FOR_LOW

    def __post_init__(self) -> None:
        if not 0 < self.points_for_medium <= self.points_for_low:
            raise ValueError("thresholds must be positive and medium must not exceed low")


DEFAULT_CONFIDENCE_PARAMS = ConfidenceParams()


@dataclass(frozen=True)
class Finding:
    """One limitation of the Report and its meaning for the confidence."""

    limitation: Limitation
    # Weight in the confidence rule of every verdict the limitation concerns.
    points: int = POINTS_DEFAULT
    # Short wording for the confidence justification; the full text when None.
    reason: str | None = None

    def concerns(self, verdict: VerdictKey) -> bool:
        """True when the limitation lowers the confidence of the verdict.

        Permanent limitations are part of every Report, so they say nothing
        about the data of this one and never lower the confidence.
        """
        if self.limitation.permanent or self.points <= 0:
            return False
        return self.limitation.affects in (verdict, "all")

    @property
    def wording(self) -> str:
        return self.reason or self.limitation.text.rstrip(". ")


def plain(limitation: Limitation) -> Finding:
    """A limitation that came without a weight, e.g. from a source adapter."""
    return Finding(limitation=limitation)
