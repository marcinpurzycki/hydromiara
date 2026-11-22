"""Waters around a parcel: distance, side, relation to the slope, facts and rules."""

from dataclasses import replace

import pytest
from shapely.geometry import LineString, box, shape

from app.catalog.recommendations import list_recommendations
from app.engine.causes import deficit_causes
from app.engine.rule_facts import rule_facts
from app.engine.rules import recommend
from app.engine.source_limitations import TOPICS
from app.engine.terrain_grid import metres_per_degree
from app.engine.water_analysis import analyse_waters, angle_between
from app.engine.water_report import water_facts, water_trace
from tests.cause_helpers import assessment, terrain, window
from tests.hydro_helpers import geometry, hydro
from tests.rule_helpers import WHEAT, ids, placed, texts, trace_of

DITCH_ENTRY = "ditch_water_retention"
LON, LAT = 18.2, 52.75
PER_LON, PER_LAT = metres_per_degree(LAT)


def at(east_m: float, north_m: float) -> tuple[float, float]:
    """Degrees of a point given in metres from the middle of the test parcel."""
    return LON + east_m / PER_LON, LAT + north_m / PER_LAT


def line(*points: tuple[float, float]) -> LineString:
    return LineString([at(*point) for point in points])


def square(west: float, south: float, east: float, north: float):
    return box(*at(west, south), *at(east, north))


# A parcel of 200 m by 200 m around the middle point.
PARCEL = geometry(square(-100, -100, 100, 100))
EAST_DITCH = ("ditch", None, line((112, -300), (112, 300)))
NORTH_STREAM = ("watercourse", "Struga", line((-400, 250), (400, 250)))
SOUTH_WEST_POND = ("water_body", None, square(-260, -260, -200, -200))


def analyse(*objects, downhill: float | None = 90.0):
    if downhill is None:
        land = terrain(0.1, 0.2)  # too flat to show a direction
    else:
        land = replace(terrain(3.0), downhill_azimuth_deg=downhill)
    return analyse_waters(hydro(*objects), PARCEL, land)


def test_distance_is_measured_from_the_outline_and_side_from_the_middle():
    result = analyse(EAST_DITCH, NORTH_STREAM, SOUTH_WEST_POND)
    ditch, stream, pond = (result.nearest[key] for key in ("ditch", "watercourse", "water_body"))
    assert ditch.distance_m == pytest.approx(12.0, abs=0.05) and ditch.side == "wschodnia"
    assert stream.distance_m == pytest.approx(150.0, abs=0.05) and stream.side == "północna"
    assert pond.distance_m == pytest.approx(141.4, abs=0.1)
    assert pond.side == "południowo-zachodnia" and pond.azimuth_deg == pytest.approx(225, abs=0.5)
    assert result.objects_count == 3
    assert list(result.nearest) == ["ditch", "watercourse", "water_body"]


def test_side_is_compared_with_the_direction_the_terrain_falls_to():
    east = analyse(EAST_DITCH, NORTH_STREAM, SOUTH_WEST_POND, downhill=90.0)
    assert east.nearest["ditch"].downhill is True
    assert east.nearest["watercourse"].downhill is False
    assert east.nearest["water_body"].downhill is False
    # North-east is within the quarter of the horizon of both east and north.
    assert analyse(EAST_DITCH, NORTH_STREAM, downhill=45.0).nearest["watercourse"].downhill
    assert analyse(EAST_DITCH, downhill=136.0).nearest["ditch"].downhill is False
    unknown = analyse(EAST_DITCH, downhill=None)
    assert unknown.nearest["ditch"].downhill is None
    assert analyse_waters(hydro(EAST_DITCH), PARCEL, None).nearest["ditch"].downhill is None
    assert angle_between(350, 10) == pytest.approx(20) and angle_between(90, 270) == 180


def test_nearest_object_of_a_group_wins_and_a_canal_counts_as_a_ditch():
    far = ("ditch", None, line((-400, -300), (-400, 300)))
    canal = ("canal", "Kanał Boczny", line((-300, -105), (300, -105)))
    result = analyse(far, EAST_DITCH, canal, ("spring", None, line((0, 0), (1, 1))))
    found = result.nearest["ditch"]
    assert found.kind == "canal" and found.name == "Kanał Boczny" and found.label == "kanał"
    assert found.distance_m == pytest.approx(5.0, abs=0.05) and found.side == "południowa"
    assert result.objects_count == 4 and "watercourse" not in result.nearest


def test_object_crossing_the_parcel_has_distance_zero():
    result = analyse(("ditch", None, line((-300, 40), (300, 40))))
    found = result.nearest["ditch"]
    assert found.distance_m == 0 and found.on_parcel
    assert found.location == "na Działce lub na jej granicy"
    through_middle = analyse(("ditch", None, line((-300, 0), (300, 0)))).nearest["ditch"]
    assert through_middle.distance_m == 0 and through_middle.location.startswith("na Działce")


def test_facts_carry_distance_side_and_slope_relation():
    facts = water_facts(analyse(EAST_DITCH, NORTH_STREAM))
    assert facts["water_objects_count"] == 2
    assert facts["ditch_distance_m"] == 12 and facts["ditch_side"] == "wschodnia"
    assert facts["ditch_location"] == "12 m od granicy Działki, strona wschodnia"
    assert facts["ditch_downhill"] is True and facts["ditch_label"] == "rów melioracyjny"
    assert facts["watercourse_name"] == "Struga" and facts["watercourse_distance_m"] == 150
    assert facts["water_body_distance_m"] is None and facts["water_body_downhill"] is None
    trace = water_trace(analyse(EAST_DITCH, NORTH_STREAM))
    assert trace.rule_id == "water.nearest" and trace.values["ditch_distance_m"] == 12
    assert "rów melioracyjny (12 m od granicy Działki, strona wschodnia)" in trace.result
    assert "nie ma rowów" in water_trace(analyse()).result


def test_retention_site_is_the_part_of_the_ditch_along_the_parcel():
    site = analyse(EAST_DITCH).site
    assert site.id == "water_object"
    assert site.label == "Odcinek rowu melioracyjnego najbliższy Działce"
    assert site.geometry.type == "LineString"
    part = shape(site.geometry.model_dump())
    # 600 m of ditch in the data; the site is only its part next to the parcel.
    assert 200 < part.length * PER_LAT < 340
    assert analyse(NORTH_STREAM, SOUTH_WEST_POND).site is None


def run(water, *, dry: bool = True, with_water: bool = True):
    """Rules of the real catalogue for a made-up parcel with the given waters."""
    given = assessment(2, 2, years=window(6, rain=150.0 if dry else 320.0), recent=(20.0, 100.0))
    land = terrain(3.0)
    causes = deficit_causes(given, WHEAT, land)
    facts = rule_facts(given, WHEAT, land, water=water if with_water else None)
    sites = {"water_object": water.site} if with_water and water.site else {}
    return recommend(causes, facts, sites=sites)


def test_ditch_at_the_parcel_triggers_the_recommendation_with_its_site():
    water = analyse(EAST_DITCH, NORTH_STREAM)
    outcome = run(water)
    assert DITCH_ENTRY in ids(outcome)
    item = placed(outcome, DITCH_ENTRY).recommendation
    assert item.group == "retencja krajobrazowa"
    assert "biegnie rów melioracyjny (12 m od granicy Działki, strona wschodnia)" in item.text
    assert item.inputs["ditch_distance_m"] == 12 and item.retention_site == water.site
    assert "najwyżej 20 m" in item.rule and item.citation


@pytest.mark.parametrize(
    "objects",
    [
        (("ditch", None, line((125, -300), (125, 300))),),  # 25 m away: past the limit
        (NORTH_STREAM, SOUTH_WEST_POND),  # no ditch in the data
        (),  # no objects at all
    ],
)
def test_without_a_ditch_at_the_parcel_the_recommendation_does_not_appear(objects):
    outcome = run(analyse(*objects))
    assert DITCH_ENTRY not in ids(outcome)
    assert trace_of(outcome, DITCH_ENTRY).result == "nie uruchomiono: warunek niespełniony"
    assert texts(outcome) == []


def test_without_water_data_the_rule_is_not_run_and_a_limitation_says_so():
    outcome = run(analyse(EAST_DITCH), with_water=False)
    assert DITCH_ENTRY not in ids(outcome)
    assert trace_of(outcome, DITCH_ENTRY).result.startswith("nie uruchomiono: brak danych")
    assert texts(outcome) == [TOPICS["hydro"].missing_text]


def test_water_entry_is_marked_provisional_like_the_other_pattern_entries():
    entry = next(item for item in list_recommendations() if item.id == DITCH_ENTRY)
    assert entry.is_provisional and entry.requires == ("water",)
    assert entry.retention_site == "water_object"
