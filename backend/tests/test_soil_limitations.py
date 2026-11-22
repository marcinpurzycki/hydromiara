"""Limitations, confidence points, cause and irrigation wording for every soil chain link."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.contracts.source_data import SourceData
from app.engine.cause_params import DEFAULT_CAUSE_PARAMS
from app.engine.cause_site_checks import soil_cause
from app.engine.cause_model import SourceNames
from app.engine.findings import POINTS_STAND_IN
from app.engine.irrigation import assess_irrigation
from app.engine.root_zone import root_zone
from app.engine.soil_limitations import (
    CATEGORY_MAP_TEXT,
    MAP_NOT_READ_TEXT,
    NO_CATEGORY_TEXT,
    NO_SOIL_TEXT,
    ORGANIC_TEXT,
    capacity_trace_values,
    soil_findings,
)
from app.orchestrator.report_builder import ReportInputs, build_report
from app.catalog.crops import get_crop
from tests.analysis_helpers import ANALYSIS_DATE, NOW
from tests.cause_helpers import assessment
from tests.engine_helpers import WHEAT, recorded_weather, source_data
from tests.irrigation_helpers import assessment_with
from tests.soil_helpers import recorded_layers, recorded_soil, soil_with

FIXTURES = Path(__file__).parent / "fixtures"
LAYERS = recorded_layers()
JULY = date(2023, 7, 5)

# Link -> (soil data, capacity source, points for the confidence, texts of this analysis).
LINKS = {
    "category map": (soil_with({3: 100.0}, layers=LAYERS), "iung_category", 0, []),
    "texture estimate": (
        soil_with({}, {11: 100.0}, LAYERS), "texture_estimate", 1, [NO_CATEGORY_TEXT],
    ),
    "texture estimate, map not read": (
        soil_with(layers=LAYERS, map_read=False), "texture_estimate", 1, [MAP_NOT_READ_TEXT],
    ),
    "stand-in": (None, "fallback", 2, [NO_SOIL_TEXT]),
    "stand-in, no category and no texture": (
        soil_with({}, {13: 100.0}), "fallback", 2, [NO_SOIL_TEXT],
    ),
    "organic soil": (soil_with({}, {5: 100.0}, LAYERS), "fallback", 2, [ORGANIC_TEXT]),
}  # fmt: skip


def findings_for(soil):
    zone = root_zone(soil, WHEAT)
    return zone, soil_findings(replace(assessment(2, 2), root_zone=zone))


@pytest.mark.parametrize("name", list(LINKS))
def test_each_link_has_its_source_points_and_text(name):
    soil, source, points, texts = LINKS[name]
    zone, findings = findings_for(soil)
    assert zone.capacity_source == source
    own = [finding for finding in findings if not finding.limitation.permanent]
    assert [finding.limitation.text for finding in own] == texts
    for verdict in ("current", "multiyear"):
        assert sum(f.points for f in findings if f.concerns(verdict)) == points
    assert all(finding.limitation.affects == "all" for finding in findings)
    permanent = [f.limitation.text for f in findings if f.limitation.permanent]
    assert permanent == ([CATEGORY_MAP_TEXT] if source == "iung_category" else [])


def test_points_follow_the_agreed_rule():
    assert POINTS_STAND_IN == 2
    _, (estimate,) = findings_for(LINKS["texture estimate"][0])
    assert estimate.points == 1 and "oszacowano z globalnej mapy gleb" in estimate.wording


def test_mixed_parcel_is_named_without_lowering_the_confidence():
    _, findings = findings_for(soil_with({3: 56.0, 1: 44.0}))
    mixed = findings[0]
    assert mixed.limitation.text == (
        "Na działce występują gleby o różnej podatności na suszę: kategoria III na 56% "
        "powierzchni, kategoria I na 44%. Wynik dotyczy działki jako całości; na słabszej "
        "części wody zabraknie wcześniej."
    )
    assert not mixed.concerns("current") and not mixed.concerns("multiyear")
    assert findings[-1].limitation.text == CATEGORY_MAP_TEXT


def test_divergent_sources_are_named_and_cost_one_point():
    zone, findings = findings_for(soil_with({4: 100.0}, layers=LAYERS))
    assert zone.capacity_source == "iung_category" and zone.taw_mm == pytest.approx(220.0)
    divergent = findings[0]
    assert "mapa IUNG-PIB wskazuje kategorię IV, a globalna mapa gleb sugeruje II" in (
        divergent.limitation.text
    )
    assert "Przyjęliśmy mapę IUNG-PIB" in divergent.limitation.text
    assert divergent.points == 1 and divergent.concerns("current")


def test_trace_values_say_what_the_capacity_rests_on():
    zone = root_zone(recorded_soil(), WHEAT)
    assert capacity_trace_values(zone) == {
        "available_water_mm_per_m": 186, "soil_category": "III",
        "category_shares": "kategoria III na 92% powierzchni", "estimated_category": "II",
    }  # fmt: skip
    assert capacity_trace_values(root_zone(None, WHEAT)) == {"available_water_mm_per_m": 150}


@pytest.mark.parametrize(
    ("soil", "state", "value"),
    [
        (soil_with({1: 100.0}), "found", 110.0),
        (soil_with({2: 100.0}), "not_found", 149.0),
        (soil_with({3: 56.0, 1: 44.0}), "not_found", 153.0),
        (soil_with({1: 60.0, 2: 40.0}), "found", 126.0),
        # Estimated category I (sand) and II (the recorded texture).
        (soil_with({}, {11: 100.0}, LAYERS), "not_found", 149.0),
        (None, "no_data", None),
        (soil_with({}, {13: 100.0}), "no_data", None),
        (soil_with({}, {5: 100.0}, LAYERS), "no_data", None),
    ],
)
def test_soil_cause_on_every_link(soil, state, value):
    zone = root_zone(soil, WHEAT)
    result = soil_cause(
        replace(assessment(2, 2), root_zone=zone), DEFAULT_CAUSE_PARAMS, SourceNames(soil="mapa")
    )
    assert (result.state, result.value) == (state, value)
    assert result.trace_values["capacity_source"] == zone.capacity_source
    if state == "no_data":
        assert "Nie można ocenić" in result.finding and not result.facts
    else:
        assert result.threshold == 140.0
        assert any("Kategoria" in fact.text or "kategoria" in fact.text for fact in result.facts)


def test_estimated_category_is_said_as_an_estimate_in_the_cause():
    zone = root_zone(soil_with({}, {11: 100.0}, LAYERS), WHEAT)
    result = soil_cause(
        replace(assessment(2, 2), root_zone=zone), DEFAULT_CAUSE_PARAMS, SourceNames()
    )
    assert "oszacowana z uziarnienia: II" in result.facts[1].text
    assert result.trace_values["soil_category"] == "II"


@pytest.mark.parametrize(
    ("soil", "words"),
    [
        (soil_with({3: 100.0}), None),
        (soil_with({}, {11: 100.0}, LAYERS), "oszacowano z globalnej mapy gleb"),
        (None, "pojemność wodną gleby przyjęto zastępczo"),
        (soil_with({}, {5: 100.0}), "glebę organiczną"),
    ],
)
def test_irrigation_names_a_weaker_soil_basis(soil, words):
    zone = root_zone(soil, WHEAT)
    outcome = assess_irrigation(assessment_with(0.8 * zone.taw_mm, JULY, zone=zone), WHEAT)
    assert outcome.trace.values["capacity_source"] == zone.capacity_source
    assert ("mniej pewne" in outcome.section.text) == (words is not None)
    if words:
        assert words in outcome.section.text
    # The amounts never exceed what the root zone can hold.
    assert outcome.section.amount_mm[1] <= round(zone.taw_mm)


def test_report_derived_from_source_data_stored_before_the_categories():
    raw = (FIXTURES / "stored" / "source_data_before_soil_categories.json").read_text()
    stored = SourceData.model_validate_json(raw)
    data = source_data(recorded_weather(), stored.soil).model_copy(
        update={"outcomes": stored.outcomes}
    )
    report = build_report(
        ReportInputs(
            report_id="r1", created_at=NOW, source_data=data, crop=get_crop("winter_wheat"),
            analysis_date=ANALYSIS_DATE,
        )  # fmt: skip
    )
    capacity = report.trace[0].values
    assert capacity["capacity_source"] == "texture_estimate"
    texts = [limitation.text for limitation in report.limitations]
    assert MAP_NOT_READ_TEXT in texts and CATEGORY_MAP_TEXT not in texts
    assert next(s for s in report.sources if s.topic == "soil").name == "ISRIC SoilGrids 2.0"
