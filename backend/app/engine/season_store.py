"""Current water status as the state of the soil water store.

Outside the crop season, and while a winter crop is dormant, the current water
status keeps its deficit level (the same stress coefficient and thresholds as
in the season; there is no separate scale for the store) but is labelled and
explained as the state of the soil water store, together with the latest
finished season and the change of the store since its end.

Pure: every function returns the same text for the same input.
"""

from datetime import date

from app.catalog.crop_model import CatalogCrop
from app.contracts.common import Scalar
from app.contracts.verdicts import CurrentStatus
from app.engine.consistency_parts import pl
from app.engine.season import PastSeason, SeasonStatus
from app.engine.season_texts import STORE_NOT_NEEDS, days, span, store_label
from app.engine.verdicts import CurrentVerdict

STORE_SUBJECT = "soil_water_store"
CROP_SUBJECT = "crop_water_needs"


def _opening(crop: CatalogCrop, status: SeasonStatus, analysis_date: date) -> str:
    if status.state == "dormant":
        return (
            f"Data analizy {pl(analysis_date)} wypada w Sezonie uprawy {crop.name_genitive}, "
            f"ale uprawa jest w spoczynku ({span(status.dormancy)}), więc {STORE_NOT_NEEDS}."
        )
    return (
        f"Data analizy {pl(analysis_date)} jest poza Sezonem uprawy {crop.name_genitive}, "
        f"więc {STORE_NOT_NEEDS}."
    )


def _past_sentences(status: SeasonStatus, past: PastSeason | None, taw_mm: float) -> list[str]:
    if past is None:
        return [
            "Dane pogodowe nie obejmują ostatniego zakończonego Sezonu uprawy, więc nie jest "
            "on opisany."
        ]
    name = "Poprzedni" if status.state == "dormant" else "Miniony"
    sentence = f"{name} Sezon uprawy ({span(past.season)}): wody brakowało przez "
    sentence += days(past.stress_days)
    if past.critical_period is not None:
        sentence += (
            f", w tym {days(past.critical_period_stress_days)} w Okresie krytycznym "
            f"({span(past.critical_period)})"
        )
    if past.days_in_balance < past.season.days:
        sentence += (
            f"; dane pogodowe obejmują {past.days_in_balance} z {past.season.days} dni sezonu"
        )
    sentences = [sentence + "."]
    if past.end_depletion_mm is not None:
        then, now = round(taw_mm - past.end_depletion_mm), round(taw_mm - past.depletion_mm)
        if now > then:
            change = f"wzrósł o {now - then} mm"
        elif now < then:
            change = f"zmalał o {then - now} mm"
        else:
            change = "nie zmienił się"
        sentences.append(
            f"Na koniec tego sezonu w glebie było {then} mm wody dostępnej dla roślin; od "
            f"tego czasu Zapas wody w glebie {change} przy {round(past.precipitation_since_mm)} "
            "mm opadu."
        )
    return sentences


def store_reason(
    crop: CatalogCrop,
    status: SeasonStatus,
    analysis_date: date,
    verdict: CurrentVerdict,
    past: PastSeason | None,
) -> str:
    """Why the level is what it is: the store today, the past season, the rebuilding."""
    taw = verdict.total_available_water_mm
    stored = round(taw - verdict.depletion_mm)
    share = round(100 * (1 - verdict.depletion_share))
    store = (
        f"Zapas wody w glebie na {pl(verdict.state_date)}: {stored} mm z {round(taw)} mm, "
        f"które gleba może zmagazynować w zasięgu korzeni ({share}%)."
    )
    opening = _opening(crop, status, analysis_date)
    return " ".join([opening, store, *_past_sentences(status, past, taw)])


def _store_details(verdict: CurrentVerdict, past: PastSeason | None) -> dict[str, Scalar]:
    taw = verdict.total_available_water_mm
    details: dict[str, Scalar] = {"soil_water_store_mm": round(taw - verdict.depletion_mm)}
    if past is None:
        return details
    then = None if past.end_depletion_mm is None else round(taw - past.end_depletion_mm)
    details.update(
        past_season_start=past.season.start.isoformat(),
        past_season_end=past.season.end.isoformat(),
        past_season_stress_days=past.stress_days,
        past_season_critical_period_stress_days=past.critical_period_stress_days,
        past_season_end_store_mm=then,
        store_change_since_season_end_mm=(
            None if then is None else details["soil_water_store_mm"] - then
        ),
        precipitation_since_season_end_mm=round(past.precipitation_since_mm),
    )
    return details


def current_status(
    base: CurrentStatus,
    crop: CatalogCrop,
    status: SeasonStatus,
    analysis_date: date,
    verdict: CurrentVerdict,
    past: PastSeason | None,
) -> CurrentStatus:
    """The current water status with what the season state adds to it.

    Every status gets `season_state` and `assessment_subject` in its details.
    An assessed status outside the season or in dormancy is also labelled and
    explained as the soil water store; the deficit level is not changed.
    """
    store = status.store_assessed and verdict.assessed
    details = {
        **base.details,
        "season_state": status.state,
        "assessment_subject": (
            STORE_SUBJECT if store else CROP_SUBJECT if verdict.assessed else None
        ),
    }
    if not store:
        return CurrentStatus(
            deficit_level=base.deficit_level,
            label=base.label,
            reason=base.reason,
            confidence=base.confidence,
            details=details,
        )
    return CurrentStatus(
        deficit_level=base.deficit_level,
        label=store_label(verdict.label),
        reason=store_reason(crop, status, analysis_date, verdict, past),
        confidence=base.confidence,
        details={**details, **_store_details(verdict, past)},
    )
