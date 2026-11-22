"""The recommendation catalogue: complete entries, honest provenance, safe texts."""

import re

import pytest
from pydantic import ValidationError

from app.catalog.crop_model import Sourced
from app.catalog.recommendation_facts import CAUSE_LABELS, FACTS, GROUP_ORDER, TOPIC_LABELS
from app.catalog.recommendation_model import AnyOf, Compare, Fired, Known, facts_read
from app.catalog.recommendations import check_catalog, get_recommendation, list_recommendations
from app.catalog.texts import MissingValue, TemplateError, fill, placeholders, polish
from app.engine.rule_facts import rule_facts
from app.engine.rules import rule_condition
from app.engine.water_analysis import analyse_waters
from tests.cause_helpers import assessment, terrain
from tests.limitation_helpers import complete_source_data
from tests.rule_helpers import WHEAT, entry, threshold

ENTRIES = list_recommendations()

# A number followed by a unit of length, area, volume or money: sizes, costs
# and parameters of a structure never appear in a recommendation.
SIZE_OR_COST = re.compile(
    r"\d\s*(m|cm|km|metr\w*|m2|m²|m3|m³|ar\w*|zł\w*|pln|eur\w*|tys\.)(?![\w²³])", re.IGNORECASE
)
# Words the project vocabulary tells to avoid, as word stems.
AVOIDED = (
    "porad", "zalec", "wskazów", "parcel", "gospodarstw", "gatun", "roślina uprawna",
    "okres wegetac", "sezon wegetac", "szczyt sezonu", "okres wrażliw", "wilgotnoś",
    "ryzyk", "susz", "czynnik", "diagnoz", "lokalizacj", "projekt", "punkt piętrzenia",
    "ostrzeże", "prognoz", "fallback",
)  # fmt: skip


def sample_facts() -> dict:
    """Facts of a parcel where every topic has data, to fill every template."""
    data = complete_source_data()
    water = analyse_waters(data.hydro, data.parcel.geometry, terrain(3.0))
    return dict(rule_facts(assessment(2, 2), WHEAT, terrain(3.0), water=water).values)


def without_measured_distance(text: str) -> str:
    """The text without the distance to an object of the water data.

    That distance is a measured fact about the surroundings of the parcel, not
    a size of anything to be built.
    """
    return re.sub(r"\(\d+ m od granicy Działki[^)]*\)", "()", text)


def filled(item) -> list[str]:
    return [fill(template, sample_facts()) for template in item.templates()]


def test_catalog_lists_every_group_in_the_order_of_the_report():
    order = [GROUP_ORDER.index(item.group) for item in ENTRIES]
    assert order == sorted(order) and set(order) == set(range(len(GROUP_ORDER)))
    assert [item.id for item in ENTRIES if "water" in item.requires] == ["ditch_water_retention"]
    assert len({item.id for item in ENTRIES}) == len(ENTRIES)
    assert get_recommendation(ENTRIES[0].id) is ENTRIES[0]
    with pytest.raises(KeyError):
        get_recommendation("unknown")


@pytest.mark.parametrize("item", ENTRIES, ids=lambda item: item.id)
def test_entry_is_complete(item):
    assert item.group in GROUP_ORDER and item.title.strip()
    assert item.causes and set(item.causes) <= set(CAUSE_LABELS)
    assert item.requires and set(item.requires) <= set(TOPIC_LABELS)
    # The rule in words names the causes and every condition.
    rule = rule_condition(item)
    assert all(CAUSE_LABELS[cause] in rule for cause in item.causes)
    assert item.text.strip() and item.gain.strip() and item.citation.strip()
    # An entry cites its source; a working content says why it is one.
    assert len(item.citation) > 20
    assert not item.is_provisional or item.provisional.strip()
    for name in item.facts_used():
        assert FACTS[name].topic in item.requires


@pytest.mark.parametrize("item", ENTRIES, ids=lambda item: item.id)
def test_templates_fill_without_gaps(item):
    for text in filled(item):
        assert "{" not in text and "}" not in text and "None" not in text
        assert "  " not in text and text == text.strip() and text.endswith(".")


@pytest.mark.parametrize("item", ENTRIES, ids=lambda item: item.id)
def test_texts_have_no_sizes_costs_or_avoided_words(item):
    for text in (*filled(item), item.title):
        assert not SIZE_OR_COST.search(without_measured_distance(text)), text
        lowered = text.lower()
        assert not [word for word in AVOIDED if word in lowered], text


def test_size_and_cost_pattern_catches_what_it_should():
    for text in ("staw o głębokości 3 m", "koszt 5000 zł", "20 m3 wody", "pas 6 metrów"):
        assert SIZE_OR_COST.search(text), text
    for text in ("w 6 z 10 lat", "od 15.05 do 30.06. W tym czasie", "20 mm opadu"):
        assert not SIZE_OR_COST.search(text), text
    measured = "biegnie rów (12 m od granicy Działki, strona wschodnia) i ma 3 m"
    assert SIZE_OR_COST.search(measured)
    assert SIZE_OR_COST.search(without_measured_distance(measured)).group(0) == "3 m"
    assert not SIZE_OR_COST.search(without_measured_distance(measured.removesuffix(" i ma 3 m")))


def test_thresholds_carry_a_source_or_a_provisional_reason():
    for item in ENTRIES:
        for condition in item.all_conditions():
            if isinstance(condition, Compare):
                assert condition.value.source or condition.value.provisional
    with pytest.raises(ValidationError):
        Sourced[int](value=1)


def test_irrigation_entry_is_conditional_and_does_not_replace_retention():
    item = ENTRIES[-1]
    assert item.group == "nawadnianie"
    assert item.text.startswith("Jeśli masz możliwość nawadniania")
    assert "nie zastępuje zatrzymywania wody" in item.text
    assert "in_season" in [name for part in item.conditions for name in facts_read(part)]


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "Spadek {slope_pct}."},  # fact of a topic that is not required
        {"text": "Wartość {unknown_fact}."},
        {"text": "Wartość {slope_pct:.1f}.", "requires": ("terrain",)},
        {"causes": ()},
        {"causes": ("soil", "soil")},
        {"requires": ("terrain", "terrain")},
        {"retention_site": "lowest_part"},  # not a retention group
        {"provisional": " "},
        {"citation": ""},
        {"conditions": (Fired(entries=("test_entry",)),)},
        {"group": "inna grupa"},
    ],
)
def test_inconsistent_entry_is_rejected(changes):
    with pytest.raises((ValidationError, TemplateError)):
        entry(**changes)


def test_conditions_are_checked_when_written():
    with pytest.raises(ValidationError):
        threshold("wysoki", "ge")
    with pytest.raises(ValidationError):
        Known(fact="unknown_fact")
    with pytest.raises(ValidationError):
        AnyOf(conditions=())
    nested = AnyOf(conditions=(threshold(5.0), Known(fact="lowest_part"), threshold(2.0)))
    assert facts_read(nested) == ("slope_pct", "lowest_part")


def test_catalog_as_a_whole_is_checked():
    first, second = entry("first"), entry("second", conditions=(Fired(entries=("first",)),))
    assert check_catalog([first, second]) == (first, second)
    with pytest.raises(ValueError, match="listed twice"):
        check_catalog([first, first])
    with pytest.raises(ValueError, match="not listed before"):
        check_catalog([second, first])


def test_template_filling():
    assert placeholders("W {a} z {b} lat, czyli {a}.") == ("a", "b")
    assert fill("W {a} z {b} lat.", {"a": 6, "b": 10, "c": 1}) == "W 6 z 10 lat."
    assert fill("Spadek {s}%, Ks {k}, całe {w}.", {"s": 1.5, "k": 0.36, "w": 3.0}) == (
        "Spadek 1,5%, Ks 0,36, całe 3."
    )
    assert (polish(True), polish(False), polish("tekst")) == ("tak", "nie", "tekst")
    for values in ({}, {"a": None}, {"a": " "}):
        with pytest.raises(MissingValue) as missing:
            fill("Wartość {a}.", values)
        assert missing.value.name == "a"
    for broken in ("{a!r}", "{a:>5}", "{0}", "{a.b}", "{", "{}"):
        with pytest.raises(TemplateError):
            placeholders(broken)
