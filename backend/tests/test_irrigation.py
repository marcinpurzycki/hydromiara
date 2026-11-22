"""Irrigation part: whether, how much and when, for every state of the analysis date."""

from datetime import date

import pytest

from app.contracts.causes import Irrigation
from app.engine.irrigation import assess_irrigation
from app.engine.root_zone import RootZone
from app.engine.season_texts import OFF_SEASON_IRRIGATION
from tests.engine_helpers import BARE_FIELD, SIMPLE_BARE_ZONE, SIMPLE_ZONE, WHEAT
from tests.irrigation_helpers import assessment_with
from tests.season_helpers import SPRING

JUNE = date(2023, 6, 20)  # winter wheat: in the season, inside the critical period
JULY = date(2023, 7, 15)  # winter wheat and the spring crop: in the season
NOVEMBER = date(2023, 11, 15)  # winter wheat dormant, the spring crop outside the season


def texts_of(section: Irrigation) -> str:
    return " ".join(filter(None, [section.text, section.timing, section.reason_if_none]))


# SIMPLE_ZONE: TAW 100 mm, p 0.5, RAW 50 mm. Ks = (100 - Dr) / 50 above RAW.
@pytest.mark.parametrize(
    ("depletion", "level", "label", "mm"),
    [
        pytest.param(95.0, 3, "silny niedobór", (45.0, 95.0), id="severe"),
        pytest.param(77.3, 2, "wyraźny niedobór", (28.0, 77.0), id="marked"),
        pytest.param(60.0, 1, "lekki niedobór", (10.0, 60.0), id="slight"),
        pytest.param(99.6, 3, "silny niedobór", (50.0, 99.0), id="close-to-taw"),
        pytest.param(100.0, 3, "silny niedobór", (50.0, 100.0), id="at-taw"),
        pytest.param(50.4, 1, "lekki niedobór", (1.0, 50.0), id="just-above-raw"),
    ],
)
def test_in_the_season_a_deficit_justifies_irrigation_with_a_range(depletion, level, label, mm):
    outcome = assess_irrigation(assessment_with(depletion, JULY), WHEAT)
    section = outcome.section
    assert outcome.kind == "justified"
    assert (section.applicable, section.justified, section.reason_if_none) == (True, True, None)
    assert section.amount_mm == mm
    assert section.amount_m3_ha == (10 * mm[0], 10 * mm[1])
    assert 0 <= mm[0] <= mm[1] <= SIMPLE_ZONE.taw_mm
    # The rounded range lies inside the range computed from the balance.
    amount = outcome.amount
    assert amount.exact_min_mm == pytest.approx(depletion - 50.0)
    assert amount.exact_max_mm == depletion
    assert amount.exact_min_mm <= amount.min_mm <= amount.max_mm <= amount.exact_max_mm
    assert f"Bieżąca sytuacja wodna na 15.07.2023: {label}." in section.text
    assert outcome.trace.values["deficit_level"] == level


def test_hand_counted_example_with_the_full_wording():
    # Dr 77.3 mm: Ks = 22.7 / 50 = 0.454, a marked deficit. Ending the stress takes
    # 77.3 - 50 = 27.3 mm (rounded up to 28), refilling the root zone 77.3 mm (down to 77).
    section = assess_irrigation(assessment_with(77.3, JUNE), WHEAT).section
    assert section.text == (
        "Jeśli masz możliwość nawadniania, jest ono teraz zasadne. Bieżąca sytuacja wodna na "
        "20.06.2023: wyraźny niedobór. W glebie zostało 23 mm wody dostępnej dla roślin "
        "z 100 mm, które gleba może zmagazynować w zasięgu korzeni. Zakres: od 28 do 77 mm "
        "wody, czyli od 280 do 770 m³ na hektar. Mniejsza z tych ilości uzupełnia Zapas wody "
        "w glebie do poziomu, od którego uprawie przestaje brakować wody, większa do pełna; "
        "więcej wody gleba w zasięgu korzeni nie zatrzyma. Podane ilości to woda, która ma "
        "wsiąknąć w glebę. To ocena ze stanu na 20.06.2023, bez prognozy pogody: opad po tym "
        "dniu zmniejsza potrzebę nawadniania, a o nawadnianiu decydujesz Ty. Nawadnianie nie "
        "zastępuje zatrzymywania wody na Działce."
    )
    assert section.timing == (
        "Teraz, według stanu na 20.06.2023: wody brakuje uprawie od 3 dni z rzędu. Data "
        "analizy wypada w Okresie krytycznym (15.05.2023–30.06.2023), w którym uprawa "
        "potrzebuje najwięcej wody i najsilniej reaguje na jej brak."
    )


def test_timing_names_the_critical_period_only_inside_it():
    outside = assess_irrigation(assessment_with(77.3, JULY), WHEAT)
    assert outside.section.timing == (
        "Teraz, według stanu na 15.07.2023: wody brakuje uprawie od 3 dni z rzędu."
    )
    assert outside.trace.values["in_critical_period"] is False
    one_day = assess_irrigation(assessment_with(77.3, JULY, days=1), WHEAT).section
    assert one_day.timing == "Teraz, według stanu na 15.07.2023: wody brakuje uprawie od 1 dnia."
    spring = assess_irrigation(assessment_with(77.3, JULY, SPRING), SPRING)
    assert "w Okresie krytycznym (01.07.2023–20.08.2023)" in spring.section.timing
    assert spring.trace.values["in_critical_period"] is True


@pytest.mark.parametrize("depletion", [0.0, 20.0, 50.0], ids=["full", "normal", "dr-equals-raw"])
def test_in_the_season_without_a_deficit_irrigation_is_not_justified(depletion):
    outcome = assess_irrigation(assessment_with(depletion, JULY), WHEAT)
    section = outcome.section
    assert outcome.kind == "not_justified" and outcome.amount is None
    assert (section.applicable, section.justified) == (True, False)
    assert section.amount_mm is section.amount_m3_ha is None
    stored = round(100 - depletion)
    assert section.reason_if_none == (
        "Nawadnianie nie jest teraz zasadne. Bieżąca sytuacja wodna na 15.07.2023: w normie. "
        f"W glebie jest {stored} mm wody dostępnej dla roślin z 100 mm, które gleba może "
        "zmagazynować w zasięgu korzeni."
    )
    assert section.text == (
        f"{section.reason_if_none} To ocena ze stanu na 15.07.2023, bez prognozy pogody: "
        "okres bez opadu po tym dniu może ją zmienić."
    )
    assert section.timing == (
        "Nie teraz. Nawadnianie stanie się zasadne, gdy Zapas wody w glebie spadnie poniżej "
        f"50 mm; na 15.07.2023 jest {stored} mm."
    )
    assert outcome.trace.result == "nie jest zasadne: brak niedoboru"


def test_outside_the_season_the_fixed_sentence_with_the_season_dates():
    for crop, day, dates, name in (
        (SPRING, NOVEMBER, "20.04.2023–10.10.2023", "uprawy jarej testowej"),
        (WHEAT, date(2023, 8, 31), "25.09.2022–31.07.2023", "pszenicy ozimej"),
    ):
        outcome = assess_irrigation(assessment_with(95.0, day, crop), crop)
        section = outcome.section
        assert outcome.kind == "out_of_season"
        assert (section.applicable, section.justified, section.timing) == (False, None, None)
        assert section.amount_mm is section.amount_m3_ha is None
        assert section.text == section.reason_if_none == (
            f"{OFF_SEASON_IRRIGATION}. Ostatni Sezon uprawy {name}: {dates}."
        )


def test_dormant_winter_crop_is_in_season_but_irrigation_is_not_justified():
    # Even a severe deficit: in dormancy the level describes the soil water store.
    outcome = assess_irrigation(assessment_with(95.0, NOVEMBER), WHEAT)
    section = outcome.section
    assert outcome.kind == "dormant" and outcome.amount is None
    assert (section.applicable, section.justified) == (True, False)
    assert section.amount_mm is section.amount_m3_ha is None
    assert section.reason_if_none == (
        "Nawadnianie nie jest teraz zasadne: uprawa jest w spoczynku (27.10.2023–15.03.2024), "
        "a Stopień niedoboru dotyczy Zapasu wody w glebie, nie potrzeb rośliny. Zapas wody "
        "w glebie na 15.11.2023: 5 mm z 100 mm."
    )
    assert section.text == (
        f"{section.reason_if_none} To ocena ze stanu na 15.11.2023, bez prognozy pogody."
    )
    assert section.timing == (
        "Nie teraz. Nawadnianie będzie oceniane ponownie, gdy uprawa ruszy ze wzrostem po "
        "spoczynku (typowo od 16.03.2024)."
    )
    assert OFF_SEASON_IRRIGATION not in texts_of(section)


def test_field_without_a_crop_is_not_applicable_with_the_reason():
    for day in (JULY, NOVEMBER):
        outcome = assess_irrigation(
            assessment_with(30.0, day, BARE_FIELD, SIMPLE_BARE_ZONE), BARE_FIELD
        )
        section = outcome.section
        assert outcome.kind == "no_crop"
        assert (section.applicable, section.justified, section.timing) == (False, None, None)
        assert section.amount_mm is section.amount_m3_ha is None
        assert section.text == section.reason_if_none == (
            "Rekomendacje nawadniania: nie dotyczy — dla Pola bez uprawy Raport ich nie "
            "przedstawia."
        )


def test_without_weather_the_need_is_not_decided():
    outcome = assess_irrigation(assessment_with(None, JULY), WHEAT)
    section = outcome.section
    assert outcome.kind == "not_assessed"
    assert (section.applicable, section.justified, section.timing) == (True, None, None)
    assert section.amount_mm is None
    assert "nie można ocenić" in section.text and section.text == section.reason_if_none
    # Outside the season the fixed sentence wins also without weather.
    off = assess_irrigation(assessment_with(None, NOVEMBER, SPRING), SPRING)
    assert off.section.text.startswith(OFF_SEASON_IRRIGATION)


@pytest.mark.parametrize(
    ("source", "words"),
    [("fallback", "pojemność wodną gleby przyjęto zastępczo"),
     ("partial_soil_profile", "obejmują tylko część głębokości")],
)
def test_a_weaker_soil_basis_is_named_next_to_the_amounts(source, words):
    zone = RootZone(depth_cm=100.0, taw_mm=100.0, depletion_fraction=0.5, capacity_source=source)
    for depletion, day in ((77.3, JULY), (20.0, JULY), (77.3, NOVEMBER)):
        outcome = assess_irrigation(assessment_with(depletion, day, zone=zone), WHEAT)
        assert words in outcome.section.text
        assert "mniej pewne" in outcome.section.text
        assert outcome.trace.values["capacity_source"] == source
    measured = assess_irrigation(assessment_with(77.3, JULY), WHEAT).section.text
    assert "mniej pewne" not in measured
