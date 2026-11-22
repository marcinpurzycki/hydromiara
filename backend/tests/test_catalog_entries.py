"""Each retention and agrotechnical entry: triggered, not triggered, and without data."""

from datetime import date

from app.catalog.crops import get_crop
from tests.rule_helpers import ids, placed, run, texts, trace_of

BARE = get_crop("bare_field")


def test_catch_crops_wording_follows_the_harvest_and_the_crop_life():
    early = placed(run(), "catch_crops").recommendation.text
    assert early.startswith("Po zbiorze pszenicy ozimej nie zostawiaj gołej gleby.")
    assert "ścierniskowy lub ozimy" in early and "GAEC 6" in early
    late = placed(run(crop=get_crop("maize")), "catch_crops").recommendation.text
    assert "wsiewkę lub międzyplon ozimy" in late and "ścierniskowy" not in late
    assert "catch_crops" not in ids(run(crop=get_crop("grassland")))
    assert "catch_crops" not in ids(run(crop=BARE))


def test_organic_matter_needs_the_soil_cause_and_soil_data():
    assert "organic_matter" not in ids(run(soil_mm=180.0))
    outcome = run(soil_mm=120.0)
    assert "(120 mm na metr)" in placed(outcome, "organic_matter").recommendation.text
    stand_in = run(soil_mm=120.0, soil_source="fallback")
    assert "organic_matter" not in ids(stand_in)


def test_contour_farming_adds_sentences_from_the_slope_thresholds():
    steep = placed(run(slope=12.0), "contour_farming").recommendation.text
    assert "sama orka w poprzek stoku nie wystarczy" in steep and "GAEC 5" not in steep
    very = placed(run(slope=14.0), "contour_farming").recommendation.text
    assert "GAEC 5" in very
    plain = placed(run(slope=8.0), "contour_farming").recommendation.text
    assert "nie wystarczy" not in plain and "GAEC 5" not in plain
    assert "contour_farming" not in ids(run(slope=5.0))
    assert "contour_farming" not in ids(run(slope=None))


def test_midfield_trees_follow_runoff_or_precipitation_with_a_clear_deficit():
    assert "midfield_trees" in ids(run(multiyear=1, slope=8.0))
    by_rain = run(multiyear=2, slope=1.0)
    assert "midfield_trees" in ids(by_rain)
    assert trace_of(by_rain, "midfield_trees").values["multiyear_deficit_level"] == 2
    assert "midfield_trees" not in ids(run(multiyear=1, slope=1.0))


def test_other_entries_apply_to_their_causes_only():
    assert "grassed_runoff_path" not in ids(run(slope=1.0))
    mulch = run(slope=1.0, soil_mm=180.0, dry=False)
    assert "crop_residue_mulch" not in ids(mulch) and "reduced_tillage" not in ids(mulch)
    assert "critical_period_watch" in ids(run(multiyear=1))
    assert "critical_period_watch" not in ids(run(multiyear=0))
    out_of_season = run(day=date(2023, 12, 1))
    assert texts(out_of_season) == []
