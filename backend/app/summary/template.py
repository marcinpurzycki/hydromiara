"""The summary put together from ready texts of the Report. Pure and repeatable.

This is the summary of every Report unless a language model answers in time
and its answer passes the check. It adds no number, date or action: every
sentence is a text of the Report, or a fixed sentence around a value of it.
"""

from app.contracts.report import Report, Summary
from app.summary import facts


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _confidence(report: Report) -> str | None:
    parts = []
    if facts.current_assessed(report):
        parts.append(f"Bieżąca sytuacja wodna — {report.current_status.confidence.level}")
    if facts.multiyear_assessed(report):
        level = report.multiyear_susceptibility.confidence.level
        parts.append(f"Podatność wieloletnia — {level}")
    return f"Pewność oceny: {'; '.join(parts)}." if parts else None


def _not_assessed(report: Report) -> str | None:
    """Says plainly that a verdict has no deficit level, with the Report's reason."""
    reasons = []
    if not facts.current_assessed(report):
        reasons.append(report.current_status.reason)
    if not facts.multiyear_assessed(report):
        reasons.append(report.multiyear_susceptibility.history_assumption)
    if not reasons:
        return None
    if len(reasons) == 2:
        subject = "Oceny nie wyznaczono."
    elif facts.current_assessed(report):
        subject = "Podatności wieloletniej nie wyznaczono."
    else:
        subject = "Bieżącej sytuacji wodnej nie wyznaczono."
    return f"{subject} {facts.first_sentence(reasons[0])}"


def _causes(report: Report) -> list[str]:
    found = facts.found_causes(report)
    sentences = []
    if found:
        names = "; ".join(facts.cause_name(cause) for cause in found)
        sentences.append(f"Stwierdzone Przyczyny niedoboru: {names}.")
    groups = facts.recommendation_groups(report)
    if groups:
        sentences.append(f"Rekomendacje w Raporcie należą do grup: {', '.join(groups)}.")
    else:
        sentences.append(facts.recommendations_note(report) or "")
    return sentences


def _irrigation(report: Report) -> list[str]:
    irrigation = report.irrigation
    sentences = [facts.first_sentence(irrigation.text)]
    if irrigation.justified and irrigation.amount_mm and irrigation.amount_m3_ha:
        low, high = irrigation.amount_mm
        low_m3, high_m3 = irrigation.amount_m3_ha
        sentences.append(
            f"Zakres: od {_number(low)} do {_number(high)} mm wody, "
            f"czyli od {_number(low_m3)} do {_number(high_m3)} m³ na hektar."
        )
    return sentences


def _consistency(report: Report) -> str:
    result = report.consistency_check.result
    sentence = f"Sprawdzenie zgodności: {result}."
    if result == "rozbieżne":
        sentence += " Ten wynik obniża Pewność oceny."
    return sentence


def _limitations(report: Report) -> list[str]:
    sentences = []
    own = facts.key_limitations(report)
    if own:
        first = facts.first_sentence(own[0].text)
        sentences.append(f"Najważniejsze Ograniczenie raportu: {first}")
    sentences.extend(item.text for item in facts.official_statement(report))
    return sentences


def template_text(report: Report) -> str:
    course = report.historical_course
    candidates = [
        report.headline,
        _not_assessed(report),
        _confidence(report),
        None if course is None else facts.first_sentence(course.comparison_sentence),
        *_causes(report),
        *_irrigation(report),
        _consistency(report),
        *_limitations(report),
    ]
    sentences: list[str] = []
    for sentence in candidates:
        sentence = (sentence or "").strip()
        # The same sentence may come from two parts of the Report.
        if sentence and not any(sentence in kept for kept in sentences):
            sentences.append(sentence)
    return " ".join(sentences)


def template_summary(report: Report) -> Summary:
    return Summary(text=template_text(report), source="template")
