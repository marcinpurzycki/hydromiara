"""Deficit causes: three states per cause, thresholds on the boundary, the gate, the trace."""

import dataclasses

import pytest

from app.contracts.causes import Cause, Recommendation
from app.engine.cause_model import CAUSE_ORDER, SourceNames
from app.engine.cause_params import CauseParams
from app.engine.causes import NO_DEFICIT_SENTENCE, causes_status, deficit_causes
from tests.cause_helpers import assessment, terrain, window, year, zone
from tests.engine_helpers import BARE_FIELD, WHEAT


def result_of(cause_id, outcome):
    return next(result for result in outcome.results if result.id == cause_id)


def check(cause_id, *, crop=WHEAT, land=terrain(), params=CauseParams(), **changes):
    outcome = deficit_causes(assessment(**changes), crop, land, params)
    return result_of(cause_id, outcome)


LOW_KC = WHEAT.model_copy(
    update={
        "id": "low_demand_crop",
        "growth": WHEAT.growth.model_copy(
            update={"kc_mid": WHEAT.growth.kc_mid.model_copy(update={"value": 0.95})}
        ),
    }
)

CASES = [
    # Precipitation as a share of ET0 in the deficit years; found below 50%.
    ("precipitation", {"years": window(6, rain=160.0)}, "found", 40.0),
    ("precipitation", {"years": window(6, rain=199.0)}, "not_found", 50.0),
    ("precipitation", {"years": window(6, rain=200.0)}, "not_found", 50.0),
    ("precipitation", {"years": window(6, rain=300.0)}, "not_found", 75.0),
    ("precipitation", {"years": window(6, rain=None)}, "no_data", None),
    # Only the current status shows a deficit: the recent days are used.
    ("precipitation", {"multiyear_level": 0, "recent": (20.0, 100.0)}, "found", 20.0),
    ("precipitation", {"multiyear_level": 0, "recent": (80.0, 100.0)}, "not_found", 80.0),
    ("precipitation", {"multiyear_level": 0, "recent": (None, None)}, "no_data", None),
    ("precipitation", {"multiyear_level": 0, "recent": (0.0, 0.0)}, "no_data", None),
    # Available water per metre of soil; found below 140 mm.
    ("soil", {"root_zone": zone(110.0)}, "found", 110.0),
    ("soil", {"root_zone": zone(139.4)}, "found", 139.0),
    ("soil", {"root_zone": zone(140.0)}, "not_found", 140.0),
    ("soil", {"root_zone": zone(216.0)}, "not_found", 216.0),
    ("soil", {"root_zone": zone(120.0, "partial_soil_profile", 60.0)}, "found", 120.0),
    ("soil", {"root_zone": zone(150.0, "fallback", 0.0)}, "no_data", None),
    ("soil", {"root_zone": zone(100.0, "fallback", 0.0)}, "no_data", None),
    # Mean slope; found above 2%.
    ("runoff", {"land": terrain(3.4)}, "found", 3.4),
    ("runoff", {"land": terrain(2.06)}, "found", 2.1),
    ("runoff", {"land": terrain(2.0)}, "not_found", 2.0),
    ("runoff", {"land": terrain(2.04)}, "not_found", 2.0),
    ("runoff", {"land": terrain(0.6, 0.5)}, "not_found", 0.6),
    ("runoff", {"land": terrain(3.0, 2.5)}, "no_data", None),
    ("runoff", {"land": terrain(status="too_few_cells")}, "no_data", None),
    ("runoff", {"land": terrain(status="unsupported_grid")}, "no_data", None),
    ("runoff", {"land": None}, "no_data", None),
    # Mid-season crop coefficient from the catalogue; found above 1.
    ("crop_demand", {"crop": WHEAT}, "found", 1.15),
    ("crop_demand", {"crop": LOW_KC}, "not_found", 0.95),
    ("crop_demand", {"crop": BARE_FIELD}, "no_data", None),
]


@pytest.mark.parametrize("cause_id, changes, state, value", CASES)
def test_cause_states(cause_id, changes, state, value):
    result = check(cause_id, **changes)
    assert result.state == state
    assert result.value == value
    cause = result.to_contract()
    assert cause.found == (state == "found")
    assert cause.indicator.value == value and cause.indicator.threshold == result.threshold
    assert cause.indicator.name and cause.finding.endswith(".")
    assert cause.recommendations == []
    if state == "no_data":
        assert cause.finding.startswith("Nie można ocenić")
    elif state == "not_found":
        assert cause.finding.startswith("Nie stwierdzono")
        assert cause.facts
    else:
        assert not cause.finding.startswith("Nie") and cause.facts
    entry = result.trace_entry()
    assert entry.rule_id == f"cause.{cause_id}"
    assert entry.result == {"found": "stwierdzono", "not_found": "nie stwierdzono", "no_data": "brak danych"}[state]
    assert entry.values["threshold"] == result.threshold


def test_precipitation_just_below_the_threshold_is_found():
    assert check("precipitation", years=window(6, rain=197.0)).state == "found"
    assert check("precipitation", years=window(6, rain=197.0)).value == 49.0


def test_thresholds_are_parameters():
    params = CauseParams(soil_min_available_water_mm_per_m=220.0, runoff_max_slope_pct=5.0)
    assert check("soil", root_zone=zone(216.0), params=params).state == "found"
    assert check("runoff", land=terrain(3.4), params=params).state == "not_found"
    with pytest.raises(ValueError):
        CauseParams(runoff_max_slope_pct=0.0)


def test_facts_give_numbers_of_the_parcel_with_their_source():
    sources = SourceNames(weather="Open-Meteo", soil="SoilGrids", terrain="Copernicus DEM")
    outcome = deficit_causes(assessment(years=window(6, rain=160.0)), WHEAT, terrain(3.4), sources=sources)
    facts = {result.id: result.facts for result in outcome.results}
    rain = facts["precipitation"][0]
    assert "2014, 2015, 2016, 2017, 2018, 2019" in rain.text
    assert "160 mm" in rain.text and "400 mm" in rain.text and rain.source.startswith("Open-Meteo")
    assert "80%" in facts["precipitation"][1].text
    assert "180 mm" in facts["soil"][0].text and facts["soil"][0].source == "SoilGrids"
    slope = facts["runoff"][0]
    assert "3,4%" in slope.text and "na północny wschód" in slope.text
    assert slope.source == "Copernicus DEM"
    assert "północno-wschodnia część Działki" in facts["runoff"][1].text
    assert "1,15" in facts["crop_demand"][0].text and "FAO" in facts["crop_demand"][0].source
    assert "Okresie krytycznym (15.05–30.06)" in facts["crop_demand"][1].text


def test_slope_above_threshold_but_within_the_scatter_says_why():
    result = check("runoff", land=terrain(3.0, 2.5))
    assert "3,0%" in result.finding and "± 2,5" in result.finding
    assert result.trace_values["direction_resolved"] is False


def test_found_causes_come_first_and_the_strongest_first():
    outcome = deficit_causes(
        assessment(root_zone=zone(70.0), years=window(6, rain=180.0)), WHEAT, terrain(1.0)
    )
    # soil: 50% below its threshold; crop: 15% above; precipitation: 10% below; runoff not found.
    assert [result.id for result in outcome.results] == ["soil", "crop_demand", "precipitation", "runoff"]
    assert [result.id for result in outcome.found] == ["soil", "crop_demand", "precipitation"]
    no_soil = deficit_causes(assessment(root_zone=zone(150.0, "fallback")), WHEAT, None)
    assert [result.state for result in no_soil.results][-2:] == ["no_data", "no_data"]
    assert [result.id for result in no_soil.results][-2:] == ["soil", "runoff"]


@pytest.mark.parametrize(
    "levels, status",
    [
        ((0, 0), "no_deficit"), ((1, 0), "determined"), ((0, 1), "determined"),
        ((3, 3), "determined"), ((None, None), "not_assessed"), ((None, 0), "no_deficit"),
        ((None, 2), "determined"), ((0, None), "no_deficit"),
    ],
)
def test_causes_are_determined_only_when_a_verdict_shows_a_deficit(levels, status):
    given = assessment(*levels)
    assert causes_status(given) == status
    outcome = deficit_causes(given, WHEAT, terrain(5.0))
    assert outcome.status == status
    if status == "determined":
        assert outcome.statement is None and len(outcome.results) == 4
        assert {result.id for result in outcome.results} == set(CAUSE_ORDER)
    else:
        assert outcome.results == () and outcome.causes() == []
        assert [entry.rule_id for entry in outcome.trace()] == ["causes.gate"]


def test_no_deficit_is_said_in_plain_words():
    outcome = deficit_causes(assessment(0, 0), WHEAT, terrain(5.0))
    assert outcome.statement == NO_DEFICIT_SENTENCE
    assert "nie stwierdzono niedoboru wody" in outcome.statement
    assert "nie przedstawiamy Rekomendacji" in outcome.statement
    one = deficit_causes(assessment(0, None), WHEAT, None)
    assert one.statement.startswith(NO_DEFICIT_SENTENCE) and "tylko jeden" in one.statement


def test_field_without_a_crop_gets_no_causes_and_no_new_rule():
    outcome = deficit_causes(assessment(None, None, crop_id="bare_field"), BARE_FIELD, terrain(5.0))
    assert outcome.status == "not_assessed" and outcome.results == ()
    assert "Przyczyn niedoboru nie wyznaczono" in outcome.statement
    assert outcome.gate.values == {"current_deficit_level": None, "multiyear_deficit_level": None}


def test_trace_is_complete_and_deterministic():
    def run():
        return deficit_causes(assessment(root_zone=zone(110.0)), WHEAT, terrain(3.4))

    trace = run().trace()
    assert [entry.rule_id for entry in trace] == [
        "causes.gate", "cause.precipitation", "cause.soil", "cause.runoff", "cause.crop_demand",
    ]
    assert trace[0].values == {"current_deficit_level": 2, "multiyear_deficit_level": 2}
    assert trace[2].values["available_water_mm_per_m"] == 110.0
    assert trace[3].values["slope_pct"] == 3.4
    assert all(entry.condition and entry.result for entry in trace)
    assert run() == run()
    assert [cause.model_dump_json() for cause in run().causes()] == [
        cause.model_dump_json() for cause in run().causes()
    ]


def test_recommendations_can_be_attached_per_cause():
    outcome = deficit_causes(assessment(root_zone=zone(110.0)), WHEAT, None)
    recommendation = Recommendation(
        id="r1", group="retencja glebowa", text="t", gain="g", rule="soil", inputs={}, citation="c"
    )
    causes = outcome.causes({"soil": [recommendation]})
    by_id = {cause.id: cause for cause in causes}
    assert by_id["soil"].recommendations == [recommendation]
    assert by_id["crop_demand"].recommendations == []
    assert all(isinstance(cause, Cause) for cause in causes)


def test_a_year_without_sums_is_left_out_of_the_precipitation_share():
    years = (*window(6, rain=160.0)[:5], dataclasses.replace(year(2019, True), precipitation_mm=None))
    result = check("precipitation", years=years + window(6)[6:])
    assert result.trace_values["years"] == 5 and result.value == 40.0
