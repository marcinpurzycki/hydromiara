"""Rule engine on the catalogue: each pattern entry triggered and not, gaps, order, trace."""

from datetime import date

import pytest

from app.catalog.recommendation_facts import CAUSE_LABELS, FACTS, GROUP_ORDER
from app.catalog.recommendations import list_recommendations
from app.contracts.causes import Recommendation
from app.engine.rule_facts import rule_facts
from tests.cause_helpers import assessment, terrain
from tests.rule_helpers import (
    entry,
    threshold,
    AGRONOMY,
    BARE_FIELD,
    DITCH,
    IRRIGATION,
    LANDSCAPE,
    SOIL,
    WHEAT,
    ids,
    placed,
    run,
    texts,
    trace_of,
)

ALL = [item.id for item in list_recommendations() if "water" not in item.requires]


def test_landscape_entry_follows_the_terrain():
    outcome = run(slope=8.0)
    item = placed(outcome, LANDSCAPE)
    assert item.cause == "runoff"
    assert "opada na północny wschód ze spadkiem 8%" in item.recommendation.text
    assert item.recommendation.inputs["slope_pct"] == 8.0
    # No geometry of the lowest part exists yet, so no retention site is given.
    assert item.recommendation.retention_site is None
    # The cause "water runs off" starts at a slope of 6%.
    assert LANDSCAPE in ids(run(slope=6.0))
    assert LANDSCAPE not in ids(run(slope=5.9))


def test_landscape_entry_is_not_triggered_on_flat_ground_or_without_its_causes():
    flat = run(slope=0.1, slope_error=0.2)
    assert LANDSCAPE not in ids(flat)
    assert trace_of(flat, LANDSCAPE).result.startswith("nie dotyczy")
    assert texts(flat) == []
    other_causes = run(slope=1.0, dry=False)
    assert LANDSCAPE not in ids(other_causes)
    assert trace_of(other_causes, LANDSCAPE).result.startswith("nie dotyczy")


def test_missing_required_data_stop_the_rule_and_leave_a_limitation():
    catalog = [entry("needs_terrain", requires=("terrain",), conditions=(threshold(3.0),))]
    outcome = run(slope=None, catalog=catalog)
    assert ids(outcome) == []
    assert trace_of(outcome, "needs_terrain").result.startswith("nie uruchomiono: brak danych o")
    assert texts(outcome) == [
        "Nie sprawdzono Rekomendacji „Pozycja needs_terrain”: brak danych o spadku "
        "i kierunku spływu wody na Działce."
    ]
    limitation = outcome.limitations[0]
    assert limitation.affects == "recommendations" and not limitation.permanent
    # Without terrain data the cause "water runs off" is not found: its entries do not apply.
    without = run(slope=None)
    assert LANDSCAPE not in ids(without) and "contour_farming" not in ids(without)
    assert SOIL in ids(without) and AGRONOMY in ids(without)


def test_soil_entry_answers_any_of_its_causes():
    by_soil = run(soil_mm=110.0, dry=False, slope=1.0)
    assert placed(by_soil, SOIL).cause == "soil"
    assert "pszenicy ozimej" in placed(by_soil, SOIL).recommendation.text
    assert placed(by_soil, SOIL).recommendation.inputs["cause_value"] == 110.0
    assert placed(run(dry=True, slope=1.0), SOIL).cause == "precipitation"
    assert placed(run(dry=False, slope=8.0), SOIL).cause == "runoff"
    none_found = run(dry=False, slope=1.0)
    assert SOIL not in ids(none_found)
    assert trace_of(none_found, SOIL).result.startswith("nie dotyczy")


@pytest.mark.parametrize(("level", "triggered"), [(0, False), (1, True), (2, True), (3, True)])
def test_agronomy_entry_starts_at_light_multiyear_deficit(level, triggered):
    outcome = run(current=2, multiyear=level)
    assert (AGRONOMY in ids(outcome)) is triggered
    assert trace_of(outcome, AGRONOMY).values["multiyear_deficit_level"] == level
    if triggered:
        text = placed(outcome, AGRONOMY).recommendation.text
        assert "W 6 z 10 ocenionych lat" in text and "od 11.05 do 10.07" in text
    else:
        assert trace_of(outcome, AGRONOMY).result == "nie uruchomiono: warunek niespełniony"
        assert texts(outcome) == []


def test_unknown_value_stops_the_rule_and_is_named():
    outcome = run(current=2, multiyear=None)
    assert AGRONOMY not in ids(outcome)
    label = FACTS["multiyear_deficit_level"].label
    assert trace_of(outcome, AGRONOMY).result == f"nie uruchomiono: brak wartości ({label})"
    assert texts(outcome) == [
        "Nie sprawdzono Rekomendacji „Obserwacja Uprawy w okresie największego "
        "zapotrzebowania na wodę”: "
        f"brak wartości „{label}”."
    ]


@pytest.mark.parametrize(("level", "triggered"), [(0, False), (1, True), (3, True)])
def test_irrigation_entry_starts_at_light_current_deficit(level, triggered):
    outcome = run(current=level, multiyear=2)
    assert (IRRIGATION in ids(outcome)) is triggered
    if triggered:
        text = placed(outcome, IRRIGATION).recommendation.text
        assert text.startswith("Jeśli masz możliwość nawadniania")
        assert placed(outcome, IRRIGATION).recommendation.inputs["in_season"] is True


def test_irrigation_entry_is_silent_outside_the_season():
    outcome = run(current=2, multiyear=2, day=date(2023, 8, 20))
    assert IRRIGATION not in ids(outcome)
    assert trace_of(outcome, IRRIGATION).values["in_season"] is False
    assert trace_of(outcome, IRRIGATION).result == "nie uruchomiono: warunek niespełniony"
    assert outcome.irrigation == () and texts(outcome) == []


def test_irrigation_entry_is_silent_for_a_dormant_winter_crop():
    outcome = run(current=2, multiyear=2, day=date(2023, 1, 15))
    values = trace_of(outcome, IRRIGATION).values
    assert (values["in_season"], values["dormant"]) == (True, True)
    assert IRRIGATION not in ids(outcome) and texts(outcome) == []


def test_irrigation_stands_apart_from_the_cause_sections():
    outcome = run()
    assert ids(outcome)[-1] == IRRIGATION
    assert [item.recommendation.id for item in outcome.irrigation] == [IRRIGATION]
    in_sections = [item for items in outcome.by_cause.values() for item in items]
    assert {item.group for item in in_sections} == set(GROUP_ORDER[:3])
    assert "części Raportu o nawadnianiu" in trace_of(outcome, IRRIGATION).result


@pytest.mark.parametrize(
    ("levels", "crop", "result"),
    [
        ((0, 0), WHEAT, "nie sprawdzano: nie wyznaczono Przyczyn niedoboru"),
        ((None, None), BARE_FIELD, "nie sprawdzano: nie wyznaczono Przyczyn niedoboru"),
    ],
    ids=["no-deficit", "field-without-a-crop"],
)
def test_without_determined_causes_there_are_no_recommendations(levels, crop, result):
    outcome = run(*levels, crop=crop)
    assert outcome.placed == () and outcome.by_cause == {} and outcome.irrigation == ()
    assert outcome.limitations == ()
    assert [entry.result for entry in outcome.trace] == [result] * len(list_recommendations())


def test_every_recommendation_has_a_found_cause_rule_values_and_source():
    outcome = run(soil_mm=110.0)
    assert sorted(ids(outcome)) == sorted(ALL) and len(set(ids(outcome))) == len(ALL)
    for item in outcome.placed:
        recommendation = item.recommendation
        assert Recommendation.model_validate(recommendation.model_dump()) == recommendation
        assert CAUSE_LABELS[item.cause] in recommendation.rule
        assert recommendation.inputs["cause"] == item.cause
        assert recommendation.inputs["cause_value"] is not None
        assert recommendation.inputs["cause_threshold"] is not None
        assert all(value is not None for value in recommendation.inputs.values())
        assert recommendation.text and recommendation.gain and recommendation.citation
        assert "{" not in recommendation.text + recommendation.gain


def test_recommendation_stands_once_under_its_strongest_found_cause():
    outcome = run(soil_mm=40.0, dry=True, slope=8.0)
    given = assessment(2, 2)
    # Soil is far below its threshold, so it is the strongest of the three causes.
    assert placed(outcome, SOIL).cause == "soil"
    sections = outcome.by_cause
    listed = [item.id for items in sections.values() for item in items]
    assert len(listed) == len(set(listed)) == len(ALL) - 1
    for items in sections.values():
        order = [GROUP_ORDER.index(item.group) for item in items]
        assert order == sorted(order)
    assert rule_facts(given, WHEAT, terrain(3.0)).available >= {"balance", "crop", "terrain"}


def test_trace_is_complete_and_the_result_is_deterministic():
    first, second = run(soil_mm=110.0), run(soil_mm=110.0)
    assert first == second
    assert [entry.rule_id for entry in first.trace] == [
        f"recommendation.{item.id}" for item in list_recommendations()
    ]
    for entry in first.trace:
        assert entry.condition.startswith("stwierdzona co najmniej jedna z Przyczyn niedoboru")
        # No ditch in the water data of this parcel, so the entry about one is not met.
        expected = "nie uruchomiono" if entry.rule_id.endswith(DITCH) else "uruchomiono"
        assert entry.result.startswith(expected) and entry.values["cause"]
    dumped = [item.recommendation.model_dump_json() for item in first.placed]
    assert dumped == [item.recommendation.model_dump_json() for item in second.placed]


def test_stand_in_soil_capacity_is_not_a_fact_about_the_parcel():
    facts = rule_facts(assessment(2, 2), WHEAT, None)
    assert "soil" in facts.available and facts.get("available_water_mm_per_m") == 180.0
    stand_in = run(soil_source="fallback", catalog=None)
    assert SOIL in ids(stand_in) and placed(stand_in, SOIL).cause != "soil"
