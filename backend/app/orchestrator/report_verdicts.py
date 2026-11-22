"""Report parts taken from the engine: the two verdicts, headline, trace.

TEMPORARY, open decision: the contract requires a deficit level 0-3 for both
verdicts, while the engine leaves a verdict without a level when it cannot be
assessed (the field without a crop, or no weather). Until the rule is decided,
such a verdict is written with the technical level 0, the label
`NOT_ASSESSED_LABEL`, `assessed: false` in the details and a limitation that
says the level is not a result. No agronomic rule is applied here.
"""

from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.contracts.common import Confidence
from app.contracts.report import Limitation, TraceEntry
from app.contracts.verdicts import CurrentStatus, MultiyearSusceptibility, MultiyearYear
from app.engine import history_texts
from app.engine.assessment import WaterAssessment
from app.engine.history import CourseResult
from app.engine.params import DEFICIT_LEVEL_LABELS, EngineParams
from app.engine.susceptibility import SusceptibilityVerdict
from app.engine.verdicts import CurrentVerdict
from app.orchestrator.report_pending import REASON_PENDING

NOT_ASSESSED_LABEL = "nie oceniono"
NOT_ASSESSED_LEVEL = 0

_NOT_ASSESSED_REASONS = {
    "no_crop": "Dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany.",
    "no_weather": "Brak danych pogodowych, z których można wyznaczyć Stopień niedoboru.",
}


def _pl(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def not_assessed_sentence(verdict: CurrentVerdict | SusceptibilityVerdict) -> str | None:
    """Why the verdict has no deficit level; None for an assessed verdict."""
    if verdict.assessed:
        return None
    return _NOT_ASSESSED_REASONS[verdict.not_assessed_reason]


def current_status(assessment: WaterAssessment, confidence: Confidence) -> CurrentStatus:
    verdict = assessment.current_status
    details = {**verdict.details(), "assessed": verdict.assessed}
    if verdict.state_date is not None:
        details["state_date"] = verdict.state_date.isoformat()
    if verdict.assessed:
        return CurrentStatus(
            deficit_level=verdict.deficit_level,
            label=verdict.label,
            reason=REASON_PENDING,
            confidence=confidence,
            details=details,
        )
    details["not_assessed_reason"] = verdict.not_assessed_reason
    return CurrentStatus(
        deficit_level=NOT_ASSESSED_LEVEL,
        label=NOT_ASSESSED_LABEL,
        reason=_NOT_ASSESSED_REASONS[verdict.not_assessed_reason],
        confidence=confidence,
        details=details,
    )


def multiyear_susceptibility(
    assessment: WaterAssessment,
    crop: CatalogCrop,
    confidence: Confidence,
    course: CourseResult | None = None,
) -> MultiyearSusceptibility:
    """`course` is the historical course; it changes only the assumption sentence."""
    verdict = assessment.multiyear_susceptibility
    # Years without weather are left out, so the list matches `total_years`.
    years = [
        MultiyearYear(year=year.year, deficit=year.deficit, partial=year.partial, values=year.values())
        for year in verdict.years
        if year.assessed
    ]
    if verdict.assessed:
        assumption = history_texts.assumption(
            f"Podatność wieloletnia jest liczona tak, jakby wybrana Uprawa ({crop.name}) "
            "rosła na Działce w każdym roku Okna wieloletniego.",
            course,
        )
    else:
        assumption = _NOT_ASSESSED_REASONS[verdict.not_assessed_reason]
    return MultiyearSusceptibility(
        deficit_years=verdict.deficit_years,
        total_years=verdict.total_years,
        deficit_level=verdict.deficit_level if verdict.assessed else NOT_ASSESSED_LEVEL,
        typical_period=None,
        confidence=confidence,
        years=years,
        history_assumption=assumption,
    )


def headline(
    assessment: WaterAssessment, analysis_date: date, current_sentence: str | None = None
) -> str:
    """Both verdicts side by side in one line; plain restatement, no interpretation.

    `current_sentence` replaces the sentence about the current water status
    (used when the level describes the soil water store).
    """
    current, multiyear = assessment.current_status, assessment.multiyear_susceptibility
    now = current.label if current.assessed else NOT_ASSESSED_LABEL
    if multiyear.assessed:
        past = f"wody brakowało w {multiyear.deficit_years} z {multiyear.total_years} lat"
    else:
        past = NOT_ASSESSED_LABEL
    first = current_sentence or f"Bieżąca sytuacja wodna na {_pl(analysis_date)}: {now}."
    return f"{first} Podatność wieloletnia: {past}."


def not_assessed_limitation(assessment: WaterAssessment) -> Limitation | None:
    reasons = {
        verdict.not_assessed_reason
        for verdict in (assessment.current_status, assessment.multiyear_susceptibility)
        if not verdict.assessed
    }
    if not reasons:
        return None
    explained = " ".join(_NOT_ASSESSED_REASONS[reason] for reason in sorted(reasons))
    return Limitation(
        text=(
            f"{explained} Werdykt oznaczony jako „{NOT_ASSESSED_LABEL}” nie jest wynikiem "
            "„w normie”."
        ),
        affects="all",
        permanent=False,
    )


def trace(assessment: WaterAssessment, params: EngineParams) -> list[TraceEntry]:
    zone = assessment.root_zone
    current, multiyear = assessment.current_status, assessment.multiyear_susceptibility
    ks = ", ".join(
        f"{label} od {_number(lowest)}"
        for label, lowest in zip(DEFICIT_LEVEL_LABELS, params.current_level_min_ks)
    )
    years = ", ".join(
        f"{label} od {lowest}"
        for label, lowest in zip(DEFICIT_LEVEL_LABELS[1:], params.susceptibility_level_min_years)
    )
    return [
        TraceEntry(
            rule_id="root_zone.capacity",
            condition="pojemność wodna strefy korzeniowej: z profilu glebowego albo zastępcza",
            values={
                "capacity_source": zone.capacity_source,
                "root_zone_depth_cm": round(zone.depth_cm),
                "total_available_water_mm": round(zone.taw_mm),
            },
            result="profil glebowy" if zone.capacity_source != "fallback" else "wartość zastępcza",
        ),
        TraceEntry(
            rule_id="current_status.level",
            condition=(
                f"Stopień niedoboru według współczynnika stresu Ks: {ks}, "
                f"poniżej {DEFICIT_LEVEL_LABELS[-1]}"
            ),
            values={
                "stress_coefficient": current.details()["stress_coefficient"],
                "state_date": None if current.state_date is None else current.state_date.isoformat(),
            },
            result=current.label if current.assessed else NOT_ASSESSED_LABEL,
        ),
        TraceEntry(
            rule_id="multiyear.deficit_years",
            condition=(
                "rok z niedoborem: co najmniej "
                f"{params.deficit_year_min_stress_days} dni stresu w Okresie krytycznym; "
                f"Stopień niedoboru według liczby takich lat: {years}"
            ),
            values={
                "deficit_years": multiyear.deficit_years,
                "total_years": multiyear.total_years,
            },
            result=multiyear.label if multiyear.assessed else NOT_ASSESSED_LABEL,
        ),
    ]
