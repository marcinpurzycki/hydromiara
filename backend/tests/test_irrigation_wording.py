"""Irrigation part: rounding, parameters, and what every answer has in common."""

import re
from dataclasses import replace
from datetime import date

import pytest

from app.contracts.causes import Irrigation
from app.engine.irrigation import RULE_ID, amount_range, assess_irrigation
from app.engine.irrigation_params import IrrigationParams
from app.engine.root_zone import RootZone
from tests.engine_helpers import SIMPLE_ZONE, WHEAT
from tests.irrigation_helpers import assessment_with
from tests.season_helpers import SPRING

JUNE = date(2023, 6, 20)
JULY = date(2023, 7, 15)
NOVEMBER = date(2023, 11, 15)
# Words the project glossary reserves or rejects.
AVOIDED = ("porad", "zalece", "wskazów", "wilgotn", "susz", "ryzyk", "wegetac", "prognozuj")
# A number followed by a unit of size, cost or equipment performance.
FORBIDDEN_UNITS = re.compile(r"\d\s*(zł|pln|eur|cm\b|km\b|m\b|m²|ha\b|kw|bar\b|l/|m³/h|godz)", re.I)


def texts_of(section: Irrigation) -> str:
    return " ".join(filter(None, [section.text, section.timing, section.reason_if_none]))


def test_amount_range_rounding():
    assert amount_range(77.3, 50.0, 1.0).mm == (28.0, 77.0)
    assert amount_range(77.3, 50.0, 5.0).mm == (30.0, 75.0)
    assert amount_range(60.0, 50.0, 1.0).mm == (10.0, 60.0)  # whole values are kept
    assert amount_range(0.1 + 0.2 + 59.7, 50.0, 1.0).mm == (10.0, 60.0)  # float noise
    assert amount_range(52.0, 50.0, 5.0).mm == (5.0, 50.0)
    # Narrower than one step: collapses to the upper end, never crosses.
    assert amount_range(4.6, 4.0, 1.0).mm == (1.0, 4.0)
    assert amount_range(1.8, 1.5, 1.0).mm == (1.0, 1.0)
    # Below a single step nothing can be rounded: the exact ends are kept.
    tiny = amount_range(0.8, 0.5, 1.0)
    assert tiny.mm == pytest.approx((0.3, 0.8))
    assert amount_range(77.3, 50.0, 1.0).m3_ha == (280.0, 770.0)


def test_a_single_value_range_reads_as_one_amount():
    zone = RootZone(depth_cm=10.0, taw_mm=3.0, depletion_fraction=0.5)
    section = assess_irrigation(assessment_with(1.8, JULY, zone=zone), WHEAT).section
    assert section.amount_mm == (1.0, 1.0)
    assert "Zakres: 1 mm wody, czyli 10 m³ na hektar." in section.text


def test_parameters_move_the_decision_and_the_rounding():
    slight = assessment_with(60.0, JULY)
    strict = assess_irrigation(slight, WHEAT, params=IrrigationParams(justified_from_level=2))
    assert strict.kind == "not_justified"
    assert strict.section.timing == (
        "Nie teraz. Nawadnianie stanie się zasadne, gdy Bieżąca sytuacja wodna wskaże co "
        "najmniej wyraźny niedobór."
    )
    coarse = assess_irrigation(
        assessment_with(77.3, JULY), WHEAT, params=IrrigationParams(amount_step_mm=5.0)
    )
    assert coarse.section.amount_mm == (30.0, 75.0)
    assert coarse.section.amount_m3_ha == (300.0, 750.0)
    with pytest.raises(ValueError):
        IrrigationParams(justified_from_level=0)
    with pytest.raises(ValueError):
        IrrigationParams(amount_step_mm=0.0)


CASES = [
    (95.0, JUNE, WHEAT), (77.3, JULY, WHEAT), (60.0, JULY, WHEAT), (50.0, JULY, WHEAT),
    (20.0, JUNE, WHEAT), (95.0, NOVEMBER, WHEAT), (95.0, NOVEMBER, SPRING),
    (77.3, JULY, SPRING), (None, JULY, WHEAT),
]


@pytest.mark.parametrize(("depletion", "day", "crop"), CASES)
def test_every_answer_is_valid_repeatable_traced_and_plainly_worded(depletion, day, crop):
    fallback = replace(SIMPLE_ZONE, capacity_source="fallback")
    for zone in (SIMPLE_ZONE, fallback):
        assessment = assessment_with(depletion, day, crop, zone)
        outcome = assess_irrigation(assessment, crop)
        section = outcome.section
        assert Irrigation.model_validate_json(section.model_dump_json()) == section
        assert assess_irrigation(assessment, crop) == outcome
        # Records after the analysis date never reach the balance and change nothing.
        later = assessment_with(depletion, day, crop, zone, later_days=20)
        assert assess_irrigation(later, crop) == outcome
        wording = texts_of(section).lower()
        assert not [word for word in AVOIDED if word in wording]
        assert not FORBIDDEN_UNITS.search(wording.replace("m³ na hektar", ""))
        assert outcome.trace.rule_id == RULE_ID
        assert outcome.trace.values["justified"] == section.justified
        assert (outcome.amount is not None) == (section.justified is True)
        if section.justified is not None:
            assert "bez prognozy pogody" in section.text
        if section.justified:
            assert section.text.startswith("Jeśli masz możliwość nawadniania")
            assert "Nawadnianie nie zastępuje zatrzymywania wody" in section.text
            assert "decydujesz Ty" in section.text
            assert outcome.trace.values["amount_min_mm"] == section.amount_mm[0]
            assert outcome.trace.values["amount_max_mm"] == section.amount_mm[1]
            assert outcome.trace.result.startswith("zasadne: od ")
        else:
            assert section.reason_if_none and section.amount_mm is None
