"""The check of a model's answer: notation may differ, content may not."""

from decimal import Decimal

import pytest

from app.summary import params
from app.summary.check import answer_problem, clean_answer
from app.summary.facts import summary_facts
from app.summary.numbers import numbers_problem, read_numbers
from tests.summary_helpers import cases

CASES = cases()
DEFICIT = summary_facts(CASES["deficit"])
SOURCE = (
    "Bieżąca sytuacja wodna na 20.06.2023: silny niedobór. Wody brakowało w 9 z 10 lat. "
    "Kc wynosi 1,15 (próg: powyżej 1,00). Opad pokrył 47% parowania. Zakres: od 63 do 179 mm "
    "wody, czyli od 630 do 1790 m³ na hektar. Okres krytyczny trwa od 15.05 do 30.06. "
    "Wody brakuje od 23 dni z rzędu. Miesiące kwiecień–lipiec."
)


def problem(answer: str, source: str = SOURCE) -> str | None:
    return numbers_problem(read_numbers(answer), read_numbers(source))


@pytest.mark.parametrize(
    "answer",
    [
        "Kc wynosi 1.15, a próg to 1,0.",
        "Kc wynosi 1,150 przy progu 1.",
        "Wody brakowało w 9 z 10 lat.",
        "W 9 z 10 ocenionych lat brakowało wody.",
        "Stan na 20.06.2023.",
        "Stan na 2023-06-20.",
        "Stan na 20 czerwca 2023 r.",
        "Stan na dzień 20.06.",
        "Okres krytyczny: 15.05–30.06, czyli od 15 maja do 30 czerwca.",
        "Opad pokrył 47 % parowania.",
        "Opad pokrył 47 procent parowania.",
        "Potrzeba 63–179 mm wody.",
        "Potrzeba od 63 mm do 179 mm wody, czyli 630-1790 m3 na hektar.",
        "To od 630 do 1 790 m³ na hektar.",
        "To od 630 do 1 790 m³ na hektar.",
        "Wody brakuje od 23 dni.",
        "W miesiącach od kwietnia do lipca opad był mały.",
        "Bez żadnej liczby też jest dobrze.",
    ],
)
def test_the_same_values_in_another_notation_are_accepted(answer):
    assert problem(answer) is None


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ("Wody brakowało w 8 z 10 lat.", "year_count_not_in_report"),
        ("Wody brakowało w 10 z 9 lat.", "year_count_not_in_report"),
        ("Kc wynosi 1,2.", "number_not_in_report"),
        ("Potrzeba 64 mm wody.", "number_not_in_report"),
        ("Potrzeba 1 790 mm wody.", "unit_changed"),
        ("Potrzeba 179 m³ wody.", "unit_changed"),
        ("Wody brakuje od 47 dni.", "unit_changed"),
        ("Stan na 21.06.2023.", "date_not_in_report"),
        ("Stan na 20.06.2024.", "date_not_in_report"),
        ("Stan na 2023-06-21.", "date_not_in_report"),
        ("Okres krytyczny kończy się 30.07.", "number_not_in_report"),
        ("Stan na 20 sierpnia 2023.", "month_not_in_report"),
        ("Plon spadnie o 15 procent.", "number_not_in_report"),
        ("Opad wyniósł 2023 mm.", "number_not_in_report"),
        ("To 3 razy więcej niż zwykle.", "number_not_in_report"),
        ("To 0,5 normy.", "number_not_in_report"),
    ],
)
def test_values_that_are_not_in_the_source_are_rejected(answer, code):
    assert problem(answer) == code


def test_reading_keeps_both_meanings_of_a_day_and_month():
    read = read_numbers("od 15.05 do 30.06.2023, Kc 1,15, zakres 1 790 m³")
    assert read.dates == {(30, 6, 2023)}
    assert read.ambiguous == [(15, 5, Decimal("15.05"))]
    assert Decimal("1.15") in read.values() and Decimal("1790") in read.values()
    assert read.units()[Decimal("1790")] == {"m3"}
    assert {5, 6} <= read.months


def test_clean_answer_makes_one_paragraph_without_quotes():
    assert clean_answer('  „Ala\n\n ma  kota.”  ') == "Ala ma kota."
    assert clean_answer("Ala „ma” kota.") == "Ala „ma” kota."


GOOD = (
    "Na 20 czerwca 2023 Bieżąca sytuacja wodna to silny niedobór, a Pewność oceny jest "
    "wysoka. "
    "Podatność wieloletnia: wody brakowało w 9 z 10 lat. Stwierdzone Przyczyny niedoboru to "
    "uprawa o dużych potrzebach wodnych oraz za mało opadów względem parowania. Jeśli masz "
    "możliwość nawadniania, jest ono teraz zasadne: od 63 do 179 mm wody."
)


def test_a_faithful_answer_is_accepted():
    assert answer_problem(GOOD, DEFICIT) is None


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ("", "answer_empty"),
        ("Za krótko.", "answer_too_short"),
        (GOOD + " Dalej." * 200, "answer_too_long"),
        (GOOD.replace("Bieżąca", "**Bieżąca**"), "answer_format"),
        (GOOD + " Zobacz https://example.org.", "answer_format"),
        (GOOD + " Na Działce panuje susza.", "drought_word"),
        (GOOD + " Gleba jest przesuszona.", "drought_word"),
        (GOOD + " Ryzyko jest duże.", "avoided_word"),
        (GOOD + " To nasza porada dla gospodarstwa.", "avoided_word"),
        (GOOD + " Wilgotność gleby jest mała.", "avoided_word"),
        (GOOD.replace("silny niedobór", "lekki niedobór"), "term_not_in_report"),
        (GOOD.replace("silny niedobór", "stan w normie"), "term_not_in_report"),
        (GOOD + " Pomoże też retencja krajobrazowa.", "term_not_in_report"),
        (GOOD + " Sprawdzenie zgodności wypadło jako rozbieżne.", "term_not_in_report"),
        (GOOD + " Trzeba też głęboko spulchnić glebę.", "term_not_in_report"),
        (GOOD.replace("jest wysoka", "jest niska"), "confidence_changed"),
        (GOOD + " To ocena o średniej pewności.", "confidence_changed"),
        (GOOD.replace("9 z 10", "7 z 10"), "year_count_not_in_report"),
        (GOOD.replace("179 mm", "180 mm"), "number_not_in_report"),
    ],
)
def test_an_unfaithful_answer_is_rejected_with_a_reason(answer, code):
    assert answer_problem(clean_answer(answer), DEFICIT) == code


def test_fixed_phrases_with_the_drought_word_are_allowed():
    answer = (
        GOOD + " Niezależny wskaźnik suszy CDI wskazuje to samo."
        " Raport nie jest urzędowym stwierdzeniem suszy rolniczej."
    )
    assert answer_problem(answer, DEFICIT) is None


def test_advice_words_are_allowed_only_when_the_report_uses_them():
    advice = " W Okresie krytycznym warto częściej sprawdzać stan Uprawy."
    assert answer_problem(GOOD + advice, DEFICIT) is None
    no_deficit = summary_facts(CASES["no_deficit"])
    plain = (
        "Bieżąca sytuacja wodna jest w normie, a w Oknie wieloletnim wody brakowało "
        "w 0 z 10 lat. Raport nie zawiera Rekomendacji retencyjnych ani agrotechnicznych."
    )
    assert answer_problem(plain, no_deficit) is None
    assert answer_problem(plain + advice, no_deficit) == "term_not_in_report"


def test_verdicts_without_a_level_must_be_reported_as_not_assessed():
    facts = summary_facts(CASES["bare_field"])
    honest = (
        "Dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany, więc oceny nie wyznaczono. "
        "Raport nie zawiera Rekomendacji."
    )
    assert answer_problem(honest, facts) is None
    silent = "Na Polu bez uprawy wszystko wygląda dobrze i Raport nie zawiera Rekomendacji."
    assert answer_problem(silent, facts) == "not_assessed_unsaid"
    invented = honest + " Sytuacja jest jednak w normie."
    assert answer_problem(invented, facts) == "level_without_assessment"


def test_deficit_scale_leads_the_guarded_terms():
    # The check reads the first four guarded terms as the degrees of the scale.
    assert len(params.GUARDED_TERMS) > 4
    for term, word in zip(params.GUARDED_TERMS, ("normie", "lekk", "wyraźn", "siln")):
        assert word in term
