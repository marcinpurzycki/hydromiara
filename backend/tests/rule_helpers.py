"""Helpers for the rule engine tests: causes, facts and catalogue entries with chosen values."""

from dataclasses import replace
from datetime import date

from app.catalog.crop_model import Sourced
from app.catalog.crops import get_crop
from app.catalog.recommendation_model import CatalogRecommendation, Compare
from app.catalog.recommendations import list_recommendations
from app.engine.causes import deficit_causes
from app.engine.rule_facts import rule_facts
from app.engine.rules import RulesOutcome, recommend
from tests.cause_helpers import assessment, terrain, window, zone

WHEAT = get_crop("winter_wheat")
BARE_FIELD = get_crop("bare_field")

LANDSCAPE = "hold_rainwater_in_lowest_part"
DITCH = "ditch_water_retention"
SOIL = "catch_crops_and_residues"
AGRONOMY = "watch_crop_in_critical_period"
IRRIGATION = "irrigation_when_water_is_short"


def run(
    current: int | None = 2,
    multiyear: int | None = 2,
    *,
    soil_mm: float = 180.0,
    soil_source: str = "soil_profile",
    dry: bool = True,
    slope: float | None = 3.0,
    slope_error: float = 0.2,
    day: date | None = None,
    crop=WHEAT,
    water: bool | None = None,
    catalog=None,
    sites=None,
) -> RulesOutcome:
    """Rules for one made-up parcel.

    `dry` makes precipitation cover less than half of the evaporation, so the
    cause "too little precipitation" is found. `slope=None` means no terrain
    data. The crop cause is always found for winter wheat. `water` says whether
    water data exist (without any object in them); by default they do for the
    real catalogue and do not for a catalogue given by the test.
    """
    water = catalog is None if water is None else water
    rain = 150.0 if dry else 320.0
    years = None
    if multiyear:
        years = window(6, rain=rain)
    given = assessment(
        current,
        multiyear,
        root_zone=zone(soil_mm, soil_source),
        years=years,
        recent=(20.0 if dry else 80.0, 100.0),
        crop_id=crop.id,
    )
    if day is not None:
        given = replace(given, analysis_date=day)
    land = None if slope is None else terrain(slope, slope_error)
    causes = deficit_causes(given, crop, land)
    facts = rule_facts(given, crop, land, water_available=water)
    return recommend(causes, facts, catalog, sites)


def ids(outcome: RulesOutcome) -> list[str]:
    return [item.recommendation.id for item in outcome.placed]


def placed(outcome: RulesOutcome, entry_id: str):
    return next(item for item in outcome.placed if item.recommendation.id == entry_id)


def trace_of(outcome: RulesOutcome, entry_id: str):
    return next(entry for entry in outcome.trace if entry.rule_id == f"recommendation.{entry_id}")


def texts(outcome: RulesOutcome) -> list[str]:
    return [limitation.text for limitation in outcome.limitations]


def entry(entry_id: str = "test_entry", **changes) -> CatalogRecommendation:
    """A catalogue entry for tests; answers the crop cause, which wheat always has."""
    fields = {
        "id": entry_id,
        "title": f"Pozycja {entry_id}",
        "group": "agrotechnika",
        "causes": ("crop_demand",),
        "text": "Tekst pozycji.",
        "gain": "Opis tego, co uzyskasz.",
        "citation": "Źródło testowe.",
    }
    return CatalogRecommendation(**(fields | changes))


def threshold(value, op: str = "ge", fact: str = "slope_pct") -> Compare:
    return Compare(
        fact=fact, op=op, value=Sourced[bool | int | float | str](value=value, source="test")
    )


def catalog_entry(entry_id: str) -> CatalogRecommendation:
    return next(item for item in list_recommendations() if item.id == entry_id)
