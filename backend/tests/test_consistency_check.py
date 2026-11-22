"""Consistency check: the table of cases, its wording and what it never reads."""

from datetime import date, timedelta

import pytest

from app.contracts.verdicts import ConsistencyCheck
from app.engine.consistency import combine
from app.engine.consistency_cdi import SOURCE as CDI_SOURCE
from app.engine.consistency_params import ConsistencyParams
from app.engine.consistency_satellite import SOURCE as SATELLITE_SOURCE
from app.sources.drought_files import CDI_CLASS_LABELS
from tests.consistency_helpers import DEKAD, IN_SEASON, OUT_OF_SEASON, cdi, run, scene
from tests.engine_helpers import BARE_FIELD

AVOIDED = ("ryzyko", "walidacj", "kontrola jakości", "fallback", "błąd", "ostrzeżenie:")


def item(outcome, source):
    return next(entry for entry in outcome.check.items if entry.source == source)


@pytest.mark.parametrize(
    ("level", "cdi_class", "expected"),
    [
        (1, 1, "zgodne"), (2, 2, "zgodne"), (3, 3, "zgodne"), (3, 1, "zgodne"),
        (1, 0, "rozbieżne"), (2, 0, "rozbieżne"), (3, 0, "rozbieżne"),
        (0, 0, "zgodne"),
        (0, 1, "rozbieżne"), (0, 2, "rozbieżne"), (0, 3, "rozbieżne"),
        (0, 4, "brak danych"), (2, 5, "brak danych"), (3, 6, "brak danych"),
        (0, None, "brak danych"), (2, None, "brak danych"),
    ],
)
def test_verdict_against_the_indicator_class(level, cdi_class, expected):
    outcome = run(level, cdi((DEKAD, cdi_class)), [scene(date(2023, 6, 15))])
    assert outcome.result == expected
    assert outcome.affects == "current"
    assert ConsistencyCheck.model_validate(outcome.check.model_dump()) == outcome.check
    entry = item(outcome, CDI_SOURCE)
    assert entry.period == "11.06.2023–20.06.2023"
    sentence = outcome.check.sentence
    assert sentence.startswith(expected.capitalize() + ".")
    if cdi_class is None:
        assert entry.value == "brak danych"
    else:
        assert entry.value == f"klasa {cdi_class}: {CDI_CLASS_LABELS[cdi_class]}"
        assert CDI_CLASS_LABELS[cdi_class] in sentence
    if expected in ("zgodne", "rozbieżne"):
        assert f"Wynik zestawienia: {expected}." in entry.meaning
        assert outcome.findings == () and "11.06.2023–20.06.2023" in sentence
    else:
        assert len(outcome.findings) == 1
        assert outcome.findings[0].limitation.affects == "current"
        assert "nie zestawiono" in sentence
    assert outcome.trace.result == expected
    assert outcome.trace.values["cdi_class"] == cdi_class
    assert outcome.trace.values["deficit_level"] == level


def test_divergence_is_described_in_plain_words():
    dry = run(2, cdi((DEKAD, 0))).check.sentence
    assert "wskazuje niedobór wody („wyraźny niedobór”)" in dry
    assert "nie wskazuje suszy (klasa 0: „brak suszy”)" in dry
    wet = run(0, cdi((DEKAD, 3))).check.sentence
    assert "nie wskazuje niedoboru wody („w normie”)" in wet
    assert "wskazuje suszę (klasa 3: „alarm: stres roślinności”)" in wet
    agree = run(3, cdi((DEKAD, 2))).check.sentence
    assert "wskazują to samo: wody brakuje" in agree
    assert "wskazują to samo: wody nie brakuje" in run(0, cdi((DEKAD, 0))).check.sentence


def test_overall_result_from_the_two_comparisons():
    assert combine(["zgodne", "zgodne"]) == "zgodne"
    assert combine(["zgodne", None]) == combine([None, "zgodne"]) == "zgodne"
    assert combine(["zgodne", "rozbieżne"]) == combine(["rozbieżne", None]) == "rozbieżne"
    assert combine([None, None]) == combine([]) == "brak danych"


@pytest.mark.parametrize(
    ("background", "analysis_date", "meaning", "own_finding", "replaces"),
    [
        (None, IN_SEASON, "Brak wskaźnika CDI dla Działki", False, False),
        (cdi((date(2023, 6, 1), 2)), IN_SEASON, "nie ma wartości dla tej dekady", True, False),
        (cdi((DEKAD, None)), IN_SEASON, "nie ma wartości dla tej dekady", True, False),
        (None, date(2015, 6, 20), "dostępny od 01.01.2016", True, True),
        # The dekad needed on 5 January 2016 is the last one of 2015.
        (cdi((date(2016, 1, 1), 3)), date(2016, 1, 5), "dostępny od 01.01.2016", True, True),
    ],
)
def test_indicator_without_a_value(background, analysis_date, meaning, own_finding, replaces):
    outcome = run(2, background, day=analysis_date)
    assert outcome.result == "brak danych"
    entry = item(outcome, CDI_SOURCE)
    assert entry.value == "brak danych" and meaning in entry.meaning
    assert "nie zestawiono z niezależnym wskaźnikiem suszy CDI" in outcome.check.sentence
    # A missing data category already has its limitation; only other gaps add one.
    assert len(outcome.findings) == int(own_finding)
    assert outcome.replaces_missing == (frozenset({"drought_background"}) if replaces else frozenset())
    if replaces:
        assert "01.01.2016" in outcome.findings[0].limitation.text


def test_first_complete_dekad_of_the_series_is_compared():
    outcome = run(2, cdi((date(2016, 1, 1), 1)), day=date(2016, 1, 10))
    assert outcome.result == "zgodne" and outcome.replaces_missing == frozenset()


def test_satellite_reading_is_described_and_never_decides():
    scenes = [scene(date(2022, 6, 12), 0.65, 0.2), scene(date(2023, 6, 15), 0.7149, None)]
    with_scene = run(3, cdi((DEKAD, 2)), scenes)
    without = run(3, cdi((DEKAD, 2)))
    assert with_scene.result == without.result == "zgodne"
    entries = [e for e in with_scene.check.items if e.source == SATELLITE_SOURCE]
    assert [e.period for e in entries] == ["15.06.2023", "12.06.2022"]
    assert entries[0].value == "NDVI 0,71; NDMI brak"
    assert "Nie wpływa na wynik" in entries[0].meaning and "Wcześniejszy" in entries[1].meaning
    assert "z 15.06.2023 (NDVI 0,71; NDMI brak) jest podany opisowo" in with_scene.check.sentence
    missing = item(without, SATELLITE_SOURCE)
    assert missing.value == "brak danych" and "Odczytów satelitarnych" in without.check.sentence
    assert with_scene.findings == without.findings == ()
    assert with_scene.trace.values["satellite_scene"] == "2023-06-15"
    assert with_scene.trace.values["satellite_result"] is None


def test_scene_older_than_the_period_is_not_the_current_reading():
    outcome = run(1, cdi((DEKAD, 1)), [scene(date(2023, 5, 20)), scene(date(2023, 6, 1), None, None)])
    entries = [e for e in outcome.check.items if e.source == SATELLITE_SOURCE]
    assert entries[0].value == "brak danych" and entries[0].period == "21.05.2023–20.06.2023"
    assert entries[1].period == "20.05.2023" and len(entries) == 2
    assert "z okresu 21.05.2023–20.06.2023 nie ma" in outcome.check.sentence
    kept = run(1, cdi((DEKAD, 1)), [scene(date(2023, 5, 21))])
    assert item(kept, SATELLITE_SOURCE).period == "21.05.2023"


def test_outside_the_season_satellite_describes_only_the_field_cover():
    dekad = date(2023, 8, 21)
    outcome = run(1, cdi((dekad, 0)), [scene(date(2023, 8, 25))], day=OUT_OF_SEASON)
    assert outcome.result == "rozbieżne"
    assert "tylko pokrywę pola, nie niedobór wody" in item(outcome, SATELLITE_SOURCE).meaning
    sentence = outcome.check.sentence
    assert "poza Sezonem uprawy, więc opisuje on tylko pokrywę pola" in sentence
    assert "Stopień niedoboru dotyczy Zapasu wody w glebie, nie potrzeb rośliny" in sentence
    in_season = run(1, cdi((DEKAD, 0)), [scene(date(2023, 6, 15))]).check
    assert "pokrywę pola, nie niedobór" not in in_season.sentence + in_season.items[1].meaning
    assert "Zapasu wody" not in in_season.sentence

    skipped = run(
        1, cdi((dekad, 0)), day=OUT_OF_SEASON, params=ConsistencyParams(cdi_compared_out_of_season=False)
    )
    assert skipped.result == "brak danych" and skipped.findings == ()
    assert "Data analizy jest poza Sezonem uprawy" in item(skipped, CDI_SOURCE).meaning


def test_both_sources_missing_is_no_data_with_both_named():
    outcome = run(3)
    assert outcome.result == "brak danych" and outcome.findings == ()
    assert [entry.value for entry in outcome.check.items] == ["brak danych", "brak danych"]
    assert {entry.source for entry in outcome.check.items} == {CDI_SOURCE, SATELLITE_SOURCE}
    assert "wskaźnika nie ma dla Działki" in outcome.check.sentence
    assert "Odczytów satelitarnych dla Działki nie ma" in outcome.check.sentence


@pytest.mark.parametrize(
    ("crop", "reason", "words"),
    [(BARE_FIELD, "no_crop", "dla Pola bez uprawy"), (None, "no_weather", "bez danych pogodowych")],
)
def test_verdict_without_a_level_is_not_compared(crop, reason, words):
    options = {} if crop is None else {"crop": crop}
    outcome = run(None, cdi((DEKAD, 0)), [scene(date(2023, 6, 15))], reason=reason, **options)
    assert outcome.result == "brak danych" and outcome.findings == ()
    assert "Sprawdzenia zgodności nie wykonano" in outcome.check.sentence
    assert words in outcome.check.sentence and "w normie" not in outcome.check.sentence
    entry = item(outcome, CDI_SOURCE)
    assert entry.value == "klasa 0: brak suszy" and "Nie zestawiono z werdyktem" in entry.meaning
    if crop is BARE_FIELD:
        assert "Pole bez uprawy: odczyt opisuje tylko pokrywę pola" in item(
            outcome, SATELLITE_SOURCE
        ).meaning
    assert outcome.trace.values["deficit_level"] is None


def test_nothing_after_the_analysis_date_changes_the_result():
    past = [(date(2023, 6, 1), 0), (DEKAD, 2)]
    scenes = [scene(date(2023, 6, 15))]
    for day in (date(2023, 6, 20), date(2023, 6, 24), date(2023, 6, 30)):
        base = run(2, cdi(*past), scenes, day=day)
        for future_class in (0, 3, None):
            later_dekads = [(date(2023, 6, 21), future_class), (date(2023, 7, 1), future_class)]
            if day == date(2023, 6, 30):  # the dekad of 21-30 June is complete on that day
                later_dekads = later_dekads[1:]
            later_scenes = [scene(day + timedelta(days=1), 0.1, -0.3), scene(date(2024, 6, 15))]
            changed = run(2, cdi(*past, *later_dekads), scenes + later_scenes, day=day)
            assert changed == base
    # The dekad that contains the date but ends after it is itself "the future".
    assert run(2, cdi((DEKAD, 0)), day=date(2023, 6, 19)).result == "brak danych"
    assert run(2, cdi((date(2023, 6, 1), 2), (DEKAD, 0)), day=date(2023, 6, 19)).result == "zgodne"


def test_same_inputs_give_the_same_outcome_and_order_does_not_matter():
    background = cdi((date(2023, 6, 1), 1), (DEKAD, 3))
    scenes = [scene(date(2022, 6, 12)), scene(date(2023, 6, 15)), scene(date(2023, 6, 5))]
    first = run(3, background, scenes)
    assert first == run(3, background, scenes)
    assert first == run(3, cdi((DEKAD, 3), (date(2023, 6, 1), 1)), list(reversed(scenes)))
    assert first.check.model_dump_json() == run(3, background, scenes).check.model_dump_json()


def test_wording_keeps_to_the_project_vocabulary():
    outcomes = [run(level, cdi((DEKAD, c)), [scene(date(2023, 6, 15))])
                for level in range(4) for c in (*range(7), None)]
    outcomes += [run(None, reason="no_crop", crop=BARE_FIELD), run(2, day=date(2015, 6, 20))]
    for outcome in outcomes:
        texts = [outcome.check.sentence, *(f.limitation.text for f in outcome.findings)]
        texts += [entry.meaning for entry in outcome.check.items]
        for text in texts:
            # Class names of the indicator are its publisher's; they are quoted, not ours.
            own = text
            for name in CDI_CLASS_LABELS.values():
                own = own.replace(name, "")
            assert not any(word in own.lower() for word in AVOIDED), text
            assert "  " not in text and not text.endswith(" ")


def test_rules_are_parameters():
    strict = ConsistencyParams(deficit_from_level=2)
    assert run(1, cdi((DEKAD, 0)), params=strict).result == "zgodne"
    assert run(1, cdi((DEKAD, 0))).result == "rozbieżne"
    recovered = ConsistencyParams(cdi_class_signals={0: "no_drought", 4: "no_drought"})
    assert run(0, cdi((DEKAD, 4)), params=recovered).result == "zgodne"
    assert run(0, cdi((DEKAD, 2)), params=recovered).result == "brak danych"
    assert item(run(1, None, [scene(date(2023, 6, 1))],
                    params=ConsistencyParams(satellite_max_scene_age_days=10)),
                SATELLITE_SOURCE).value == "brak danych"
    with pytest.raises(ValueError):
        ConsistencyParams(deficit_from_level=0)


def test_dormant_winter_crop_is_compared_as_the_soil_water_store():
    day = date(2023, 11, 20)  # winter wheat: in the season, dormant
    outcome = run(1, cdi((date(2023, 11, 11), 1)), [scene(date(2023, 11, 15))], day=day)
    assert outcome.result == "zgodne"
    assert "Uprawa jest w spoczynku, więc Stopień niedoboru dotyczy Zapasu wody" in (
        outcome.check.sentence
    )
    assert "poza Sezonem uprawy" not in outcome.check.sentence
    # A dormant crop is in its season: the satellite reading is not "cover only".
    assert "pokrywę pola, nie niedobór" not in outcome.check.sentence
