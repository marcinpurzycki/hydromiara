"""The simulation engine on made-up crops: ranking, ties, crops without a verdict."""

import time
from dataclasses import replace
from datetime import date

from app.engine.assessment import assess_water
from app.engine.limitations import SIMULATION_LIMITATIONS
from app.engine.params import DEFAULT_PARAMS
from app.engine.simulation import TOP_COUNT, simulate
from app.engine.simulation_texts import ranking_limitations
from tests.engine_helpers import (
    BARE_FIELD,
    WHEAT,
    recorded_soil,
    recorded_weather,
    source_data,
)
from tests.simulation_helpers import LATE, made_crop, many_crops, weather_with_dry_years

DAY = date(2023, 6, 20)
RECORDED = source_data(recorded_weather(), recorded_soil())
DRY = {2015, 2018, 2019}


def dry_years_data(first: date = date(2012, 9, 1), dry: set[int] = DRY, **options):
    return source_data(weather_with_dry_years(first, date(2023, 12, 31), dry, **options))


def ids(results) -> list[str]:
    return [result.crop.id for result in results]


def numbers(result) -> tuple[int, int]:
    return result.verdict.deficit_years, result.verdict.total_years


def test_current_crop_equals_the_verdict_of_the_report_engine():
    simulation = simulate(RECORDED, WHEAT, DAY, many_crops(6))
    assert simulation.current.crop == WHEAT
    assert simulation.current.verdict == assess_water(RECORDED, WHEAT, DAY).multiyear_susceptibility
    # Every other crop is assessed by the same entry point too.
    for result in simulation.ranked:
        assert result.verdict == assess_water(RECORDED, result.crop, DAY).multiyear_susceptibility


def test_ranking_is_ascending_and_never_holds_the_current_crop():
    crops = [*many_crops(8), WHEAT, BARE_FIELD]
    simulation = simulate(RECORDED, WHEAT, DAY, crops)
    assert len(simulation.ranked) == 8 and len(simulation.top) == TOP_COUNT
    assert simulation.top == simulation.ranked[:TOP_COUNT]
    assert WHEAT.id not in ids(simulation.ranked)
    keys = [(r.deficit_share, r.stress_days_per_year) for r in simulation.ranked]
    assert keys == sorted(keys)
    # The made-up crops do differ on this weather, so the order is not trivial.
    assert len({numbers(result) for result in simulation.ranked}) > 1


def test_same_share_is_ordered_by_stress_days_then_by_the_crop_list():
    # Without any rain every year is a deficit year for every crop, and every
    # day of a critical period is a stress day: only the length of the period
    # differs. Critical periods: 47 days (15.05-30.06) and 16 days (15.05-30.05).
    never_rains = source_data(
        weather_with_dry_years(date(2012, 9, 1), date(2023, 12, 31), set(range(2012, 2024)))
    )
    long_a, long_b = made_crop("long_a"), made_crop("long_b")
    short = made_crop("short", critical=((5, 15), (5, 30)))
    current = made_crop("current")
    simulation = simulate(never_rains, current, date(2023, 8, 1), [long_b, long_a, short])
    assert [numbers(result) for result in simulation.ranked] == [(10, 10)] * 3
    assert ids(simulation.ranked) == ["short", "long_b", "long_a"]
    assert [r.stress_days_per_year for r in simulation.ranked] == [16, 47, 47]
    # Identical crops keep the order of the list they came in.
    swapped = simulate(never_rains, current, date(2023, 8, 1), [long_a, long_b, short])
    assert ids(swapped.ranked) == ["short", "long_a", "long_b"]


def test_different_numbers_of_assessed_years_are_compared_by_share():
    # The weather starts in 2014. On 20 June 2023 the early crop has the years
    # 2014-2023 (all assessed), the late one 2013-2022 (2013 without weather).
    data = dry_years_data(first=date(2014, 1, 1))
    early, late = made_crop("early"), made_crop("late", shape="spring")
    simulation = simulate(data, made_crop("current"), DAY, [late, early])
    by_id = {result.crop.id: result for result in simulation.ranked}
    assert numbers(by_id["early"]) == (3, 10) and numbers(by_id["late"]) == (3, 9)
    # Three deficit years each; three of ten is a smaller share than three of nine.
    assert ids(simulation.ranked) == ["early", "late"]

    texts = [item.text for item in ranking_limitations(simulation)]
    assert any("z różnej liczby lat (od 9 do 10)" in text for text in texts)
    same_years = simulate(data, made_crop("current"), DAY, [early])
    assert not any("różnej liczby lat" in item.text for item in ranking_limitations(same_years))


def test_fewer_than_three_other_crops_and_none_at_all():
    two = simulate(RECORDED, WHEAT, DAY, [WHEAT, *many_crops(2)])
    assert len(two.top) == 2 and two.not_compared == ()
    texts = [item.text for item in ranking_limitations(two)]
    assert texts[:2] == [item.text for item in SIMULATION_LIMITATIONS]
    assert "porównano 2 inne Uprawy" in texts[2] and "mniej niż trzy" in texts[2]

    for crops in ([WHEAT], [], [WHEAT, BARE_FIELD]):
        alone = simulate(RECORDED, WHEAT, DAY, crops)
        assert alone.top == () and alone.current.assessed
        assert "tylko bieżącą Uprawę" in ranking_limitations(alone)[2].text


def test_field_without_a_crop_is_left_out_and_named():
    simulation = simulate(RECORDED, WHEAT, DAY, [BARE_FIELD, *many_crops(4), WHEAT])
    assert BARE_FIELD.id not in ids(simulation.ranked)
    assert ids(simulation.not_compared) == [BARE_FIELD.id]
    assert simulation.other(BARE_FIELD.id).verdict.not_assessed_reason == "no_crop"
    limitations = ranking_limitations(simulation)
    assert all(item.affects == "multiyear" for item in limitations)
    assert [item.permanent for item in limitations] == [True, True, False, False]
    assert "porównano 4 inne Uprawy z listy" in limitations[2].text
    assert limitations[3].text.startswith("Pole bez uprawy nie jest porównywane")


def test_field_without_a_crop_as_the_current_crop_has_no_verdict():
    simulation = simulate(RECORDED, BARE_FIELD, DAY, [WHEAT, BARE_FIELD])
    assert not simulation.current.assessed
    assert ids(simulation.ranked) == [WHEAT.id]


def test_crop_without_weather_in_its_critical_periods_is_not_ranked():
    # Weather of one spring only: the late crop has no day in any critical period.
    short = source_data(weather_with_dry_years(date(2023, 3, 1), DAY, set()))
    late = made_crop("late", shape="spring", critical=LATE)
    simulation = simulate(short, made_crop("current"), DAY, [late])
    assert simulation.ranked == () and ids(simulation.not_compared) == ["late"]
    assert simulation.not_compared[0].verdict.not_assessed_reason == "no_weather"
    assert "Uprawa testowa late" in ranking_limitations(simulation)[3].text


def test_wording_avoids_the_excluded_terms():
    simulation = simulate(RECORDED, WHEAT, DAY, [BARE_FIELD, *many_crops(7)])
    text = " ".join(item.text for item in ranking_limitations(simulation)).lower()
    for word in ("prognoz", "doradc", "rekomendacj", "najleps", "najmocniejsz", "roślin"):
        assert word not in text


def test_simulation_is_deterministic_and_ignores_days_after_the_analysis_date():
    crops = [*many_crops(5), BARE_FIELD]
    first = simulate(RECORDED, WHEAT, DAY, crops)
    assert simulate(RECORDED, WHEAT, DAY, crops) == first
    # The recorded weather runs to the end of 2023; cutting it at the analysis
    # date, or replacing what follows with a drought, changes nothing.
    until = [day for day in recorded_weather() if day.date <= DAY]
    assert simulate(source_data(until, recorded_soil()), WHEAT, DAY, crops) == first
    drought = until + weather_with_dry_years(date(2023, 6, 21), date(2023, 12, 31), {2023})
    assert simulate(source_data(drought, recorded_soil()), WHEAT, DAY, crops) == first


def test_parameters_are_shared_by_all_crops():
    strict = replace(DEFAULT_PARAMS, deficit_year_min_stress_days=40)
    simulation = simulate(RECORDED, WHEAT, DAY, many_crops(3), strict)
    assert simulation.current.verdict == (
        assess_water(RECORDED, WHEAT, DAY, strict).multiyear_susceptibility
    )
    assert simulation.current.verdict != simulate(RECORDED, WHEAT, DAY, []).current.verdict


def test_twenty_crops_are_simulated_well_within_the_answer_time():
    crops = [*many_crops(20), BARE_FIELD]
    started = time.perf_counter()
    simulation = simulate(RECORDED, WHEAT, DAY, crops)
    elapsed = time.perf_counter() - started
    assert len(simulation.ranked) == 20
    # The answer must come within 2 s; the engine alone takes a fraction of it.
    assert elapsed < 2.0
