"""Rule mechanism on made-up entries: every kind of condition, water data, sites, gaps."""

import pytest

from app.catalog.recommendation_model import (
    Addition,
    AllOf,
    AnyOf,
    CauseFound,
    Fired,
    Known,
)
from app.contracts.causes import RetentionSite
from app.contracts.common import GeoJsonGeometry
from app.engine.limitations import report_findings
from app.engine.rule_conditions import Context, describe, evaluate
from app.engine.rule_facts import RuleFacts
from app.engine.source_limitations import TOPICS
from tests.cause_helpers import assessment
from tests.limitation_helpers import complete_source_data, without
from tests.rule_helpers import entry, ids, placed, run, texts, threshold, trace_of

WATER_TEXT = TOPICS["hydro"].missing_text


def ditch_entry(entry_id: str = "ditch", **changes):
    return entry(entry_id, group="retencja krajobrazowa", requires=("water",), **changes)


def test_entry_that_needs_water_data_is_not_run_without_them():
    outcome = run(catalog=[ditch_entry()])
    assert outcome.placed == ()
    result = trace_of(outcome, "ditch").result
    assert result == (
        "nie uruchomiono: brak danych o ciekach, rowach i zbiornikach w otoczeniu Działki"
    )
    assert texts(outcome) == [WATER_TEXT]
    assert outcome.limitations[0].affects == "recommendations"
    assert ids(run(catalog=[ditch_entry()], water=True)) == ["ditch"]


def test_missing_water_data_are_named_once_in_the_report():
    outcome = run(catalog=[ditch_entry("a"), ditch_entry("b")])
    assert texts(outcome) == [WATER_TEXT]
    data = without(complete_source_data(), "hydro")
    findings = report_findings(data, assessment(2, 2), last=outcome.limitations)
    assert [finding.limitation.text for finding in findings].count(WATER_TEXT) == 1


def test_entries_stopped_by_the_same_gap_share_one_limitation():
    catalog = [
        entry("a", requires=("terrain",), title="Pierwsza"),
        entry("b", requires=("terrain", "water"), title="Druga"),
    ]
    outcome = run(slope=None, catalog=catalog)
    assert texts(outcome) == [
        "Nie sprawdzono Rekomendacji „Pierwsza”, „Druga”: brak danych o spadku i kierunku "
        "spływu wody na Działce.",
        WATER_TEXT,
    ]


@pytest.mark.parametrize(
    ("slope", "triggered"), [(4.9, False), (5.0, True), (5.1, True)], ids=["below", "at", "above"]
)
def test_threshold_at_its_boundary(slope, triggered):
    catalog = [entry(requires=("terrain",), conditions=(threshold(5.0, "ge"),))]
    outcome = run(slope=slope, catalog=catalog)
    assert bool(outcome.placed) is triggered
    assert trace_of(outcome, "test_entry").values["slope_pct"] == slope
    strict = [entry(requires=("terrain",), conditions=(threshold(5.0, "gt"),))]
    assert bool(run(slope=slope, catalog=strict).placed) is (slope > 5.0)


def test_text_that_needs_an_unknown_value_stops_the_rule():
    catalog = [entry(requires=("terrain",), text="Najniższa część: {lowest_part}.")]
    outcome = run(slope=0.1, slope_error=0.2, catalog=catalog)
    assert outcome.placed == ()
    assert texts(outcome) == [
        "Nie sprawdzono Rekomendacji „Pozycja test_entry”: brak wartości „najniższa część "
        "Działki”."
    ]


def test_entry_may_depend_on_another_entry_and_on_a_named_cause():
    catalog = [
        entry("steep", requires=("terrain",), conditions=(threshold(5.0),)),
        entry("follows", conditions=(Fired(entries=("steep",)),)),
        entry("by_runoff", conditions=(CauseFound(cause="runoff"),)),
    ]
    assert ids(run(slope=6.0, catalog=catalog)) == ["steep", "follows", "by_runoff"]
    assert ids(run(slope=3.0, catalog=catalog)) == ["by_runoff"]
    assert ids(run(slope=1.0, catalog=catalog)) == []
    rule = placed(run(slope=6.0, catalog=catalog), "by_runoff").recommendation.rule
    assert "stwierdzono Przyczynę niedoboru „woda szybko odpływa z pola”" in rule


def test_additions_extend_the_text_only_when_their_conditions_hold():
    steep = Addition(text="Spadek to {slope_pct}%.", conditions=(threshold(5.0),))
    always = Addition(text="Omów to z doradcą rolniczym.")
    catalog = [entry(requires=("terrain",), additions=(steep, always))]
    gentle = placed(run(slope=3.0, catalog=catalog), "test_entry").recommendation
    assert gentle.text == "Tekst pozycji. Omów to z doradcą rolniczym."
    assert "slope_pct" not in gentle.inputs
    sloped = placed(run(slope=6.0, catalog=catalog), "test_entry").recommendation
    assert sloped.text == "Tekst pozycji. Spadek to 6%. Omów to z doradcą rolniczym."
    assert sloped.inputs["slope_pct"] == 6.0


def test_retention_site_comes_only_from_derived_geometry():
    site = RetentionSite(
        id="lowest_part",
        label="Najniższa część Działki",
        geometry=GeoJsonGeometry(type="Point", coordinates=[18.2, 52.75]),
    )
    catalog = [entry(group="retencja glebowa", retention_site="lowest_part", link="simulation")]
    assert placed(run(catalog=catalog), "test_entry").recommendation.retention_site is None
    given = placed(run(catalog=catalog, sites={"lowest_part": site}), "test_entry")
    assert given.recommendation.retention_site == site
    assert given.recommendation.link == "simulation"


def context(**values) -> Context:
    return Context(RuleFacts(values=values), found_causes={"soil"}, fired={"earlier"})


def test_conditions_have_three_outcomes():
    high, low = threshold(5.0, "ge"), threshold(2.0, "lt")
    assert evaluate(high, context(slope_pct=6.0)) is True
    assert evaluate(high, context(slope_pct=4.0)) is False
    assert evaluate(high, context()) is None
    assert evaluate(high, context(slope_pct="stromo")) is None
    known = Known(fact="lowest_part")
    assert evaluate(known, context()) is False
    assert evaluate(known, context(lowest_part="północna")) is True
    assert evaluate(CauseFound(cause="soil"), context()) is True
    assert evaluate(CauseFound(cause="runoff"), context()) is False
    assert evaluate(Fired(entries=("other", "earlier")), context()) is True
    either, both = AnyOf(conditions=(high, known)), AllOf(conditions=(high, known))
    assert evaluate(either, context(lowest_part="północna")) is True
    assert evaluate(either, context()) is None
    assert evaluate(either, context(slope_pct=1.0)) is False
    assert evaluate(both, context(lowest_part="północna")) is None
    assert evaluate(both, context()) is False
    assert evaluate(both, context(slope_pct=6.0, lowest_part="północna")) is True
    assert evaluate(threshold(True, "eq", "in_season"), context(in_season=False)) is False
    assert evaluate(threshold("ok", "ne", "current_label"), context(current_label="x")) is True
    assert evaluate(AllOf(conditions=(high, low)), context(slope_pct=6.0)) is False


def test_conditions_are_worded_in_polish():
    assert describe(threshold(5.0, "ge")) == "średni spadek terenu Działki, %: co najmniej 5"
    assert describe(threshold(1.5, "lt")) == "średni spadek terenu Działki, %: poniżej 1,5"
    assert describe(Known(fact="lowest_part")) == "znana wartość: najniższa część Działki"
    nested = AnyOf(conditions=(CauseFound(cause="soil"), Fired(entries=("a", "b"))))
    assert describe(nested) == (
        "(stwierdzono Przyczynę niedoboru „gleba słabo magazynuje wodę” lub "
        "uruchomiono Rekomendację: a lub b)"
    )
