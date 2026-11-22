"""Interpretation of the satellite reading: cover, change, earlier years, crop match."""

from datetime import date, timedelta

import pytest

from app.contracts.analyses import CropHistory
from app.engine.satellite_reading import DEFAULT_READING_PARAMS
from tests.consistency_helpers import IN_SEASON, OUT_OF_SEASON, run, scene
from tests.engine_helpers import WHEAT
from tests.season_helpers import SPRING

SAME = CropHistory(same_every_year=True)
DORMANT = date(2023, 1, 15)
BEFORE_CRITICAL = date(2023, 4, 28)  # in the season, before the critical period (from 15 May)


def window(newest: float, *earlier: float, ndvi: float = 0.8, day: date = IN_SEASON) -> list:
    """Scenes of the current window: the newest NDMI and the earlier ones, three days apart."""
    ndmis = (newest, *earlier)
    return [
        scene(day - timedelta(days=1 + 3 * position), ndvi, ndmi)
        for position, ndmi in enumerate(ndmis)
    ]


def years(*ndmi_by_year: tuple[int, float]) -> list:
    """One scene on the same day of each given year."""
    return [scene(IN_SEASON.replace(year=year), 0.8, ndmi) for year, ndmi in ndmi_by_year]


def facts(outcome) -> dict:
    return outcome.trace.values


def test_thresholds_of_the_reading():
    assert DEFAULT_READING_PARAMS.significant_change == 0.10
    assert DEFAULT_READING_PARAMS.min_same_crop_years == 3
    assert DEFAULT_READING_PARAMS.april_min_ndvi == 0.4
    assert (DEFAULT_READING_PARAMS.history_years, DEFAULT_READING_PARAMS.history_half_window_days) == (5, 15)


@pytest.mark.parametrize(
    ("day", "crop", "items", "words", "limited"),
    [
        (IN_SEASON, WHEAT, 3, "Nie stosujemy progów bezwzględnych", False),
        (BEFORE_CRITICAL, WHEAT, 1, "tylko w Okresie krytycznym", False),
        (DORMANT, WHEAT, 1, "tylko w Okresie krytycznym", False),
        (OUT_OF_SEASON, WHEAT, 1, "poza Sezonem uprawy", True),
    ],
)
def test_cover_is_described_always_and_the_rest_only_in_the_critical_period(
    day, crop, items, words, limited
):
    outcome = run(2, scenes=[scene(day - timedelta(days=2)), scene(day - timedelta(days=9))], day=day)
    satellite = outcome.check.items[1:]
    assert len(satellite) == items
    assert satellite[0].value == "NDVI 0,71; NDMI 0,23" and words in satellite[0].meaning
    assert all("Nie wpływa na wynik Sprawdzenia zgodności." in item.meaning for item in satellite)
    assert [f.limitation.affects for f in outcome.findings] == (["current"] if limited else [])
    if items == 1:
        assert facts(outcome)["satellite_signal"] == "cover_only"
        assert facts(outcome)["satellite_ndmi_change"] is None


def test_field_without_a_crop_gets_the_cover_only():
    from app.catalog.crops import get_crop

    outcome = run(None, scenes=window(0.2, 0.4), crop=get_crop("bare_field"), reason="no_crop")
    assert len(outcome.check.items) == 2 and "Pole bez uprawy" in outcome.check.items[1].meaning
    assert outcome.findings == ()


def test_outside_the_season_the_reading_lowers_the_confidence_of_the_current_status():
    outcome = run(1, scenes=[scene(OUT_OF_SEASON - timedelta(days=3))], day=OUT_OF_SEASON)
    (finding,) = outcome.findings
    assert finding.concerns("current") and not finding.concerns("multiyear")
    assert "opisują tylko, czy pole jest pokryte roślinami" in finding.limitation.text
    assert run(1, scenes=None, day=OUT_OF_SEASON).findings == ()  # the missing reading is named once


@pytest.mark.parametrize(
    ("ndmis", "value", "change"),
    [
        ((0.20, 0.32, 0.30, 0.34), "NDMI spada o 0,12", -0.12),
        ((0.20, 0.30), "NDMI spada o 0,10", -0.10),  # the threshold itself is a change
        ((0.21, 0.30), "NDMI bez zmian (−0,09)", -0.09),
        ((0.30, 0.25, 0.35), "NDMI bez zmian (+0,00)", 0.0),
        ((0.45, 0.30), "NDMI rośnie o 0,15", 0.15),
        ((0.20, 0.30, 0.30, 0.90), "NDMI spada o 0,10", -0.10),  # median, not mean
    ],
)
def test_direction_of_change_against_the_median_of_earlier_scenes(ndmis, value, change):
    outcome = run(0, scenes=window(*ndmis))
    item = outcome.check.items[2]
    assert item.value == value and item.period == "21.05.2023–20.06.2023"
    assert facts(outcome)["satellite_ndmi_change"] == pytest.approx(change)
    assert f"jest ich {len(ndmis) - 1}" in item.meaning and "0,10" in item.meaning


def test_one_scene_is_not_enough_for_a_direction():
    outcome = run(2, scenes=window(0.2) + [scene(IN_SEASON - timedelta(days=40), 0.8, 0.6)])
    assert outcome.check.items[2].value == "brak danych"
    assert "co najmniej dwóch odczytów" in outcome.check.items[2].meaning
    assert facts(outcome)["satellite_signal"] == "not_enough_data"


@pytest.mark.parametrize(
    ("level", "ndmis", "signal", "words"),
    [
        (2, (0.20, 0.35), "confirms", "go potwierdza"),
        (2, (0.33, 0.35), "does_not_confirm", "nie jest to rozbieżność"),
        (0, (0.20, 0.35), "contradicts", "NDMI istotnie spada w Okresie krytycznym"),
        (0, (0.33, 0.35), "no_objection", "nie pokazuje istotnego spadku"),
    ],
)
def test_what_the_reading_says_next_to_the_balance_never_changes_the_result(
    level, ndmis, signal, words
):
    outcome = run(level, scenes=window(*ndmis))
    assert facts(outcome)["satellite_signal"] == signal
    assert words in outcome.check.items[2].meaning and words in outcome.check.sentence
    assert outcome.result == "brak danych"  # no drought indicator here; the reading decides nothing
    assert facts(outcome)["satellite_result"] is None
    assert outcome.findings == ()


def test_without_a_crop_history_earlier_years_are_not_compared():
    outcome = run(2, scenes=window(0.2, 0.22) + years((2022, 0.5), (2021, 0.5), (2020, 0.5)))
    item = outcome.check.items[3]
    assert (item.value, item.period) == ("nie porównano", "wcześniejsze lata")
    assert "Nie wiemy, co rosło na Działce" in item.meaning and "Historię upraw" in item.meaning
    assert facts(outcome)["satellite_same_crop_years"] is None
    assert facts(outcome)["satellite_signal"] == "does_not_confirm"


def test_with_the_same_crop_in_three_years_ndmi_is_compared_with_their_median():
    scenes = window(0.23, 0.22) + years((2022, 0.40), (2021, 0.44), (2020, 0.38))
    outcome = run(2, scenes=scenes, crop_history=SAME)
    item = outcome.check.items[3]
    assert item.value == "NDMI niższy o 0,17 niż w latach tej samej Uprawy"
    assert item.period == "lata 2020, 2021, 2022"
    assert facts(outcome)["satellite_ndmi_vs_years"] == pytest.approx(-0.17)
    # Lower than in the years of the same crop confirms the deficit even without a fall.
    assert facts(outcome)["satellite_signal"] == "confirms"
    similar = run(2, scenes=window(0.36, 0.35) + scenes[2:], crop_history=SAME)
    assert similar.check.items[3].value == "NDMI zbliżony do lat tej samej Uprawy (−0,04)"


def test_only_years_the_history_names_with_the_same_crop_count():
    scenes = window(0.23, 0.22) + years((2022, 0.40), (2021, 0.44), (2020, 0.38), (2019, 0.41))
    named = CropHistory(years={2022: "winter_wheat", 2021: "bare_field", 2020: "winter_wheat"})
    outcome = run(2, scenes=scenes, crop_history=named)
    item = outcome.check.items[3]
    # 2021 grew something else and 2019 is not named: two years are not enough.
    assert (item.value, item.period) == ("brak danych", "lata 2020, 2022")
    assert "co najmniej 3 lat" in item.meaning and "takich lat jest 2" in item.meaning
    assert facts(outcome)["satellite_ndmi_vs_years"] is None
    enough = CropHistory(years={2022: "winter_wheat", 2020: "winter_wheat", 2019: "winter_wheat"})
    assert run(2, scenes=scenes, crop_history=enough).check.items[3].period == "lata 2019, 2020, 2022"


def test_year_value_is_the_median_of_its_scenes_within_15_days_of_the_same_day():
    day = IN_SEASON.replace(year=2022)
    scenes = window(0.30, 0.30) + years((2021, 0.50), (2020, 0.50)) + [
        scene(day - timedelta(days=15), 0.8, 0.40),
        scene(day + timedelta(days=15), 0.8, 0.60),
        scene(day + timedelta(days=16), 0.8, 0.99),  # outside the window of the year
        scene(IN_SEASON.replace(year=2017), 0.8, 0.99),  # more than five years back
    ]
    outcome = run(2, scenes=scenes, crop_history=SAME)
    assert outcome.check.items[3].period == "lata 2020, 2021, 2022"
    assert facts(outcome)["satellite_ndmi_vs_years"] == pytest.approx(0.30 - 0.50)


@pytest.mark.parametrize(
    ("ndvis", "mismatch"), [((0.23, 0.24), True), ((0.39,), True), ((0.40,), False), ((0.2, 0.7, 0.8), False)]
)
def test_winter_crop_with_a_bare_field_in_april_does_not_match_the_scenes(ndvis, mismatch):
    scenes = [scene(date(2023, 4, 27 - 3 * n), ndvi, -0.2) for n, ndvi in enumerate(ndvis)]
    scenes.append(scene(date(2022, 4, 20), 0.1, -0.3))  # April of another year does not count
    outcome = run(1, scenes=scenes, day=BEFORE_CRITICAL)
    assert facts(outcome)["satellite_crop_mismatch"] is mismatch
    assert outcome.result == "brak danych"
    if not mismatch:
        assert outcome.findings == ()
        return
    (finding,) = outcome.findings
    assert finding.concerns("current") and finding.concerns("multiyear")
    assert "nie pasują do Uprawy ozimej" in finding.limitation.text
    assert "Sprawdź, czy wybrana Uprawa jest właściwa" in finding.limitation.text


def test_crop_without_reading_rules_is_described_and_nothing_is_concluded():
    april = [scene(date(2023, 4, 20), 0.1, -0.3)]
    assert run(1, scenes=april, day=date(2023, 4, 28), crop=SPRING).findings == ()
    day = date(2023, 7, 20)  # in the critical period of the spring crop of the tests
    outcome = run(2, scenes=window(0.20, 0.35, day=day), day=day, crop=SPRING)
    assert outcome.check.items[2].value == "NDMI spada o 0,15"
    assert facts(outcome)["satellite_signal"] == "cover_only"
    assert "potwierdza" not in outcome.check.sentence


def test_history_that_names_other_crops_gives_no_year_to_compare():
    scenes = window(0.23, 0.22) + years((2022, 0.40), (2021, 0.44), (2020, 0.38))
    other = CropHistory(years={2022: "bare_field", 2021: "bare_field"})
    item = run(2, scenes=scenes, crop_history=other).check.items[3]
    assert (item.value, item.period) == ("brak danych", "wcześniejsze lata")
    assert "takich lat jest 0" in item.meaning and "Nie wiemy" not in item.meaning


def test_reading_rules_by_crop_and_the_safe_default():
    from app.catalog.crops import list_crops
    from app.catalog.periods import crosses_new_year
    from app.engine.satellite_crops import BY_CROP, DEFAULT, crop_reading

    wheat = crop_reading("winter_wheat")
    assert wheat.signals_deficit and wheat.green_in_april and wheat.change_indices == ("ndmi",)
    assert crop_reading("winter_rapeseed").green_in_april and "kwitnienia" in crop_reading("winter_rapeseed").note
    assert not crop_reading("maize").green_in_april and crop_reading("maize").signals_deficit
    assert not crop_reading("potato").signals_deficit and not crop_reading("sugar_beet").signals_deficit
    assert crop_reading("grassland").change_indices == ("ndvi", "ndmi")
    assert crop_reading("bare_field") is DEFAULT and crop_reading("not_in_the_list") is DEFAULT
    assert not DEFAULT.signals_deficit and not DEFAULT.green_in_april
    assert all(rules.source and rules.note for rules in BY_CROP.values())
    catalogue = {crop.id: crop for crop in list_crops()}
    assert set(BY_CROP) <= set(catalogue)  # no rule for a crop the catalogue does not have
    for crop in catalogue.values():  # every crop of the catalogue can be read
        rules = crop_reading(crop.id)
        assert rules.change_indices
        if rules.green_in_april:  # only crops sown in autumn: their season crosses the new year
            assert crosses_new_year(crop.season)


def test_crops_read_with_both_indices_or_only_descriptively():
    day = date(2023, 7, 20)
    scenes = [scene(day - timedelta(days=1), 0.50, 0.20), scene(day - timedelta(days=4), 0.75, 0.35)]
    grass = run(2, scenes=scenes, day=day, crop=SPRING.model_copy(update={"id": "grassland"}))
    assert grass.check.items[2].value == "NDVI spada o 0,25; NDMI spada o 0,15"
    assert facts(grass)["satellite_signal"] == "confirms"
    assert facts(grass)["satellite_ndvi_change"] == pytest.approx(-0.25)
    potato = run(2, scenes=scenes, day=day, crop=SPRING.model_copy(update={"id": "potato"}))
    assert potato.check.items[2].value == "NDMI spada o 0,15"
    assert facts(potato)["satellite_signal"] == "cover_only"
    assert "podajemy tylko opisowo" in potato.check.items[1].meaning
