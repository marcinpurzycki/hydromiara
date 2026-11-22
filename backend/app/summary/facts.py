"""What the summary is made from: a selection of the finished Report, nothing else.

The selection holds ready texts and numbers of the result. It leaves out
everything that identifies the place: the parcel identifier and number, the
administrative names, the geometry, the map and the report identifier. A text
that names any of them, or that holds a coordinate, is dropped as a whole.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.catalog.recommendation_facts import CAUSE_LABELS
from app.contracts.causes import Cause
from app.contracts.report import Limitation, Report
from app.engine.limitations import PERMANENT_LIMITATIONS
from app.engine.params import DEFICIT_LEVEL_LABELS
from app.orchestrator.report_pending import REASON_PENDING
from app.summary import params

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ„])")
# A number with four or more decimals; dates such as 20.06.2023 are not matched.
_COORDINATE = re.compile(r"(?<![\d.,])\d{1,3}[.,]\d{4,}(?![\d.,])")


@dataclass(frozen=True)
class SummaryFacts:
    """The selection as sent to the model and as the answer is checked against."""

    payload: dict[str, Any]
    current_assessed: bool
    multiyear_assessed: bool

    @property
    def text(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False, indent=1)

    @property
    def any_assessed(self) -> bool:
        return self.current_assessed or self.multiyear_assessed


def pl_date(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def first_sentence(text: str) -> str:
    return _SENTENCE_END.split(text.strip(), maxsplit=1)[0]


def current_assessed(report: Report) -> bool:
    return report.current_status.details.get("assessed") is not False


def multiyear_assessed(report: Report) -> bool:
    return report.multiyear_susceptibility.total_years > 0


def found_causes(report: Report) -> list[Cause]:
    return [cause for cause in report.causes if cause.found]


def cause_name(cause: Cause) -> str:
    return CAUSE_LABELS.get(cause.id, cause.id)


def recommendation_groups(report: Report) -> list[str]:
    """Groups of the recommendations in the Report, in the order they appear."""
    groups: list[str] = []
    for cause in found_causes(report):
        for recommendation in cause.recommendations:
            if recommendation.group not in groups:
                groups.append(recommendation.group)
    return groups


def key_limitations(report: Report) -> list[Limitation]:
    """Limitations of this analysis that concern a verdict, as ordered in the Report."""
    return [
        limitation for limitation in report.limitations
        if not limitation.permanent and limitation.affects != "recommendations"
    ]


def official_statement(report: Report) -> list[Limitation]:
    """The permanent limitation saying the Report is no official drought statement."""
    return [item for item in report.limitations if item == PERMANENT_LIMITATIONS[0]]


def _place_patterns(report: Report) -> list[re.Pattern[str]]:
    parcel = report.meta.parcel
    names = (
        parcel.parcel_id, parcel.number, parcel.region, parcel.commune, parcel.county,
        parcel.voivodeship, report.meta.report_id, report.meta.derived_from,
    )
    return [
        re.compile(rf"(?<![\w/]){re.escape(name.strip())}(?![\w/])", re.IGNORECASE)
        for name in names
        if name and len(name.strip()) >= 2
    ]


def _without_places(value: Any, patterns: list[re.Pattern[str]]) -> Any:
    """The value without texts that identify the place; empty parts are removed."""
    if isinstance(value, str):
        named = _COORDINATE.search(value) or any(p.search(value) for p in patterns)
        return None if named or not value.strip() else value
    if isinstance(value, dict):
        cleaned = {key: _without_places(item, patterns) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item not in (None, [], {})}
    if isinstance(value, list):
        cleaned = [_without_places(item, patterns) for item in value]
        return [item for item in cleaned if item not in (None, [], {})]
    return value


def _causes(report: Report) -> list[dict[str, Any]]:
    return [
        {
            "nazwa": cause_name(cause),
            "ustalenie": cause.finding,
            "rekomendacje": [
                {"grupa": item.group, "tekst": item.text, "co_uzyskasz": item.gain}
                for item in cause.recommendations
            ],
        }
        for cause in found_causes(report)
    ]


def summary_facts(report: Report) -> SummaryFacts:
    current, multiyear = report.current_status, report.multiyear_susceptibility
    has_current, has_multiyear = current_assessed(report), multiyear_assessed(report)
    current_part: dict[str, Any] = {"oceniono": has_current, "ocena": current.label}
    if current.reason != REASON_PENDING:
        current_part["uzasadnienie"] = current.reason
    multiyear_part: dict[str, Any] = {"oceniono": has_multiyear}
    if has_current:
        current_part["pewnosc_oceny"] = current.confidence.level
        current_part["pewnosc_dlaczego"] = current.confidence.why
    if has_multiyear:
        multiyear_part.update(
            zdanie=(
                f"wody brakowało w {multiyear.deficit_years} z {multiyear.total_years} lat"
            ),
            stopien_niedoboru=DEFICIT_LEVEL_LABELS[multiyear.deficit_level],
            typowy_okres=multiyear.typical_period,
            pewnosc_oceny=multiyear.confidence.level,
            pewnosc_dlaczego=multiyear.confidence.why,
        )
    else:
        multiyear_part["uzasadnienie"] = multiyear.history_assumption
    course = report.historical_course
    payload = {
        "uprawa": report.meta.crop.name,
        "data_analizy": pl_date(report.meta.analysis_date),
        "naglowek": report.headline,
        "sezon_uprawy": report.season.note,
        "biezaca_sytuacja_wodna": current_part,
        "podatnosc_wieloletnia": multiyear_part,
        "przebieg_historyczny": None if course is None else course.comparison_sentence,
        "przyczyny_niedoboru": _causes(report),
        "rekomendacje_uwaga": recommendations_note(report),
        "nawadnianie": {"tekst": report.irrigation.text, "termin": report.irrigation.timing},
        "sprawdzenie_zgodnosci": {
            "wynik": report.consistency_check.result,
            "zdanie": report.consistency_check.sentence,
        },
        "ograniczenia": [
            limitation.text
            for limitation in (
                *key_limitations(report)[: params.MAX_LIMITATIONS],
                *official_statement(report),
            )
        ],
    }
    return SummaryFacts(
        payload=_without_places(payload, _place_patterns(report)),
        current_assessed=has_current,
        multiyear_assessed=has_multiyear,
    )


def recommendations_note(report: Report) -> str | None:
    """The sentence about missing recommendations; None when the Report has some."""
    if recommendation_groups(report):
        return None
    if not (current_assessed(report) or multiyear_assessed(report)):
        reason = "Bez oceny nie wyznacza się Przyczyn niedoboru, więc"
    elif not found_causes(report):
        reason = "Nie stwierdzono żadnej Przyczyny niedoboru, więc"
    else:
        reason = "Żadna reguła Rekomendacji nie została spełniona, więc"
    return f"{reason} Raport nie zawiera Rekomendacji retencyjnych ani agrotechnicznych."
