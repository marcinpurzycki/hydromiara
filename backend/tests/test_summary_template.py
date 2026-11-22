"""The template summary: made of Report texts only, repeatable, right for every situation."""

import pytest

from app.contracts.report import Report
from app.summary import params
from app.summary.check import answer_problem
from app.summary.facts import first_sentence, summary_facts
from app.summary.numbers import read_numbers
from app.summary.template import template_summary, template_text
from tests.summary_helpers import cases

CASES = cases()


@pytest.mark.parametrize("name", CASES)
def test_template_is_the_summary_of_every_built_report(name):
    report = CASES[name]
    assert report.summary == template_summary(report)
    assert report.summary.source == "template"
    assert Report.model_validate_json(report.model_dump_json()) == report
    assert not any(entry.rule_id == "summary.source" for entry in report.trace)
    assert not any("nie wyznacza jeszcze" in item.text for item in report.limitations)


@pytest.mark.parametrize("name", CASES)
def test_template_is_short_repeatable_and_passes_the_check_made_for_the_model(name):
    report = CASES[name]
    text = report.summary.text
    assert text == template_text(report) == template_text(report.model_copy(deep=True))
    assert params.MIN_ANSWER_CHARS < len(text) <= params.MAX_ANSWER_CHARS
    assert "  " not in text and "\n" not in text and "None" not in text
    # No avoided word, no number or date from outside the Report, no changed unit.
    assert answer_problem(text, summary_facts(report)) is None


@pytest.mark.parametrize("name", CASES)
def test_every_number_of_the_template_is_in_the_report(name):
    report = CASES[name]
    whole_report = read_numbers(report.model_dump_json(exclude={"summary", "meta", "map"}))
    in_summary = read_numbers(report.summary.text)
    assert {token.value for token in in_summary.tokens} <= whole_report.values()
    assert report.headline in report.summary.text


def test_deficit_names_the_causes_the_groups_and_the_irrigation_range():
    report = CASES["deficit"]
    text = report.summary.text
    found = [cause for cause in report.causes if cause.found]
    assert found and "Stwierdzone Przyczyny niedoboru: " in text
    assert "uprawa o dużych potrzebach wodnych" in text
    for cause in found:
        for recommendation in cause.recommendations:
            assert recommendation.group in text
    low, high = report.irrigation.amount_mm
    assert f"od {low:g} do {high:g} mm wody" in text
    assert "Jeśli masz możliwość nawadniania" in text
    # Both verdicts stand next to each other, with their own confidence.
    assert report.current_status.label in text
    multiyear = report.multiyear_susceptibility
    assert f"w {multiyear.deficit_years} z {multiyear.total_years} lat" in text
    assert f"Bieżąca sytuacja wodna — {report.current_status.confidence.level}" in text
    assert f"Podatność wieloletnia — {multiyear.confidence.level}" in text
    assert text.endswith("Raport nie jest urzędowym stwierdzeniem suszy rolniczej.")


def test_without_a_deficit_the_summary_says_there_are_no_recommendations():
    report = CASES["no_deficit"]
    assert report.current_status.deficit_level == 0
    assert report.multiyear_susceptibility.deficit_years == 0 and report.causes == []
    text = report.summary.text
    assert "Nie stwierdzono żadnej Przyczyny niedoboru" in text
    assert "Raport nie zawiera Rekomendacji" in text
    assert "Stwierdzone Przyczyny" not in text and "Zakres:" not in text
    assert "Nawadnianie nie jest teraz zasadne." in text


@pytest.mark.parametrize("name", ["out_of_season", "dormant"])
def test_outside_the_growing_season_the_summary_speaks_of_the_soil_water_store(name):
    report = CASES[name]
    text = report.summary.text
    assert "Zapas wody w glebie" in text
    assert first_sentence(report.irrigation.text) in text and "Zakres:" not in text
    assert ("poza Sezonem uprawy" in text) == (name == "out_of_season")
    assert ("w spoczynku" in text) == (name == "dormant")


def test_field_without_a_crop_says_that_nothing_was_assessed():
    report = CASES["bare_field"]
    text = report.summary.text
    assert "Oceny nie wyznaczono." in text
    assert "Dla Pola bez uprawy Stopień niedoboru nie jest wyznaczany." in text
    assert "Pewność oceny:" not in text and "w normie" not in text
    assert "Raport nie zawiera Rekomendacji" in text
    facts = summary_facts(report)
    assert not facts.any_assessed
    assert "stopien_niedoboru" not in facts.payload["podatnosc_wieloletnia"]


def test_missing_soil_is_the_limitation_the_summary_names():
    report = CASES["no_soil"]
    text = report.summary.text
    assert "Najważniejsze Ograniczenie raportu: Brak danych o glebie Działki" in text
    assert "Najważniejsze Ograniczenie raportu" not in CASES["deficit"].summary.text


def test_divergent_consistency_check_is_said_with_its_effect():
    report = CASES["divergent"]
    assert report.consistency_check.result == "rozbieżne"
    text = report.summary.text
    assert "Sprawdzenie zgodności: rozbieżne. Ten wynik obniża Pewność oceny." in text
    assert "Sprawdzenie zgodności: zgodne." in CASES["deficit"].summary.text


def test_crop_history_adds_only_the_comparison_sentence():
    report, plain = CASES["with_history"], CASES["deficit"]
    sentence = first_sentence(report.historical_course.comparison_sentence)
    assert sentence in report.summary.text
    assert report.summary.text.replace(f" {sentence}", "") == plain.summary.text
