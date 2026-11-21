"""Confidence of each of the two verdicts: a word and the reasons behind it.

Working rule (no source gives one; the weights and thresholds are named
parameters in `findings.py`):
- only limitations that concern the verdict count: those marked for it or for
  both verdicts; limitations of the recommendations concern neither;
- permanent limitations never count, because they are in every Report;
- each limitation that counts adds its points; the level follows from the sum;
- a verdict that could not be assessed gets the lowest level, with the reason.

The two verdicts are judged separately and never combined. The result depends
only on the arguments.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.contracts.common import Confidence, ConfidenceLevel
from app.engine.findings import (
    DEFAULT_CONFIDENCE_PARAMS,
    ConfidenceParams,
    Finding,
    VerdictKey,
)

HIGH: ConfidenceLevel = "wysoka"
MEDIUM: ConfidenceLevel = "średnia"
LOW: ConfidenceLevel = "niska"

WHY_COMPLETE = (
    "Dane, z których wyznaczono ten werdykt, są kompletne: nie dotyczy go żadne "
    "Ograniczenie raportu poza stałymi."
)
WHY_NOT_ASSESSED = "Pewności oceny nie można wtedy określić, dlatego podano najniższy poziom."


def counted(findings: Sequence[Finding], verdict: VerdictKey) -> list[Finding]:
    """The limitations that lower the confidence of the verdict, in report order."""
    return [finding for finding in findings if finding.concerns(verdict)]


def confidence_points(findings: Sequence[Finding], verdict: VerdictKey) -> int:
    return sum(finding.points for finding in counted(findings, verdict))


def confidence_level(
    points: int, params: ConfidenceParams = DEFAULT_CONFIDENCE_PARAMS
) -> ConfidenceLevel:
    """The level for a sum of points; each threshold is inclusive."""
    if points >= params.points_for_low:
        return LOW
    if points >= params.points_for_medium:
        return MEDIUM
    return HIGH


def assess_confidence(
    verdict: VerdictKey,
    findings: Sequence[Finding],
    *,
    not_assessed: str | None = None,
    params: ConfidenceParams = DEFAULT_CONFIDENCE_PARAMS,
) -> Confidence:
    """Confidence of one verdict.

    `findings` are all limitations of the Report, including the divergent
    consistency check when there is one. `not_assessed` is the sentence that
    says why the verdict has no deficit level; None for an assessed verdict.
    """
    if not_assessed is not None:
        return Confidence(level=LOW, why=f"{not_assessed} {WHY_NOT_ASSESSED}")
    reasons = counted(findings, verdict)
    level = confidence_level(sum(finding.points for finding in reasons), params)
    if not reasons:
        return Confidence(level=level, why=WHY_COMPLETE)
    verb = "obniża" if len(reasons) == 1 else "obniżają"
    listed = "; ".join(finding.wording for finding in reasons)
    return Confidence(level=level, why=f"Pewność oceny {verb}: {listed}.")


@dataclass(frozen=True)
class VerdictConfidences:
    """Confidence of the current water status and of the multi-year susceptibility."""

    current: Confidence
    multiyear: Confidence


def verdict_confidences(
    findings: Sequence[Finding],
    *,
    current_not_assessed: str | None = None,
    multiyear_not_assessed: str | None = None,
    params: ConfidenceParams = DEFAULT_CONFIDENCE_PARAMS,
) -> VerdictConfidences:
    """Both confidences from the same limitations; they are never averaged."""
    return VerdictConfidences(
        current=assess_confidence(
            "current", findings, not_assessed=current_not_assessed, params=params
        ),
        multiyear=assess_confidence(
            "multiyear", findings, not_assessed=multiyear_not_assessed, params=params
        ),
    )
