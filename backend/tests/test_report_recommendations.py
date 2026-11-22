"""Recommendations in the Report: from the builder and from the whole analysis."""

from app.catalog.recommendations import list_recommendations
from app.contracts.report import Report
from app.engine.causes import NO_DEFICIT_SENTENCE
from app.engine.source_limitations import TOPICS
from app.orchestrator.report_causes import causes_part
from tests.analysis_helpers import ANALYSIS_DATE, start, wait_finished
from tests.rule_helpers import AGRONOMY, IRRIGATION, LANDSCAPE, SOIL
from tests.terrain_helpers import grid, plane
from tests.test_report_causes import _assessed, build, by_id, data_with, texts, wet_days

RULE_IDS = [f"recommendation.{entry.id}" for entry in list_recommendations()]


def recommendations(report: Report) -> list:
    return [item for cause in report.causes for item in cause.recommendations]


def rule_trace(report: Report) -> list:
    return [entry for entry in report.trace if entry.rule_id.startswith("recommendation.")]


def test_deficit_report_has_recommendations_under_found_causes():
    report = build(data_with(grid(plane(3.0, 45))))
    listed = recommendations(report)
    assert [item.id for item in listed] and len({item.id for item in listed}) == len(listed)
    assert {item.id for item in listed} == {LANDSCAPE, SOIL, AGRONOMY}
    for cause in report.causes:
        assert cause.found or cause.recommendations == []
        for item in cause.recommendations:
            assert item.inputs["cause"] == cause.id
            assert item.inputs["cause_value"] == cause.indicator.value
            assert item.inputs["cause_threshold"] == cause.indicator.threshold
            assert item.rule and item.citation and item.text and item.gain
    landscape = next(item for item in listed if item.id == LANDSCAPE)
    assert "opada na północny wschód" in landscape.text and landscape.retention_site is None
    assert report.map.retention_sites == []
    assert [entry.rule_id for entry in rule_trace(report)] == RULE_IDS


def test_irrigation_is_not_among_the_cause_sections():
    data = data_with(grid(plane(3.0, 45)))
    report = build(data)
    assert report.current_status.deficit_level >= 1 and report.season.in_season
    assert all(item.group != "nawadnianie" for item in recommendations(report))
    irrigation = next(e for e in rule_trace(report) if e.rule_id.endswith(IRRIGATION))
    assert irrigation.result.startswith("uruchomiono")
    assert "części Raportu o nawadnianiu" in irrigation.result
    # The triggered entry is kept for the irrigation part of the Report.
    part = causes_part(data, *_assessed(data))
    assert [item.recommendation.id for item in part.irrigation] == [IRRIGATION]
    assert report.irrigation.justified is None


def test_report_without_deficit_has_no_recommendations_and_says_so_once():
    report = build(wet_days(data_with(grid(plane(3.0, 45)))))
    assert report.causes == [] and recommendations(report) == []
    assert texts(report).count(NO_DEFICIT_SENTENCE) == 1
    assert [entry.rule_id for entry in rule_trace(report)] == RULE_IDS
    assert all(entry.result.startswith("nie sprawdzano") for entry in rule_trace(report))
    assert not any(text.startswith("Nie sprawdzono Rekomendacji") for text in texts(report))


def test_field_without_a_crop_has_no_recommendations():
    report = build(data_with(grid(plane(3.0, 45))), "bare_field")
    assert report.causes == [] and recommendations(report) == []
    assert all(entry.result.startswith("nie sprawdzano") for entry in rule_trace(report))


def test_missing_terrain_names_the_recommendation_that_was_not_checked():
    report = build(data_with(None))
    assert LANDSCAPE not in {item.id for item in recommendations(report)}
    named = [text for text in texts(report) if text.startswith("Nie sprawdzono Rekomendacji")]
    assert len(named) == 1 and "spadku i kierunku spływu" in named[0]
    limitation = next(item for item in report.limitations if item.text == named[0])
    assert limitation.affects == "recommendations" and not limitation.permanent
    # Missing water data are named once, by the limitation of the missing category.
    assert texts(report).count(TOPICS["hydro"].missing_text) == 1
    assert len(set(texts(report))) == len(report.limitations)
    # Limitations about recommendations do not lower the confidence of a verdict.
    with_terrain = build(data_with(grid(plane(3.0, 45))))
    assert report.current_status.confidence == with_terrain.current_status.confidence


def test_same_inputs_give_the_same_recommendations():
    first = build(data_with(grid(plane(3.0, 45))))
    second = build(data_with(grid(plane(3.0, 45))))
    assert first.model_dump_json() == second.model_dump_json()
    assert by_id(first)["crop_demand"].recommendations == by_id(second)["crop_demand"].recommendations


def test_whole_analysis_gives_a_valid_report_with_recommendations(client):
    report_id = start(client)
    assert wait_finished(client, report_id)["state"] == "done"
    body = client.get(f"/api/reports/{report_id}").json()
    report = Report.model_validate(body)
    assert report.meta.analysis_date == ANALYSIS_DATE
    listed = recommendations(report)
    assert listed and all(item.group != "nawadnianie" for item in listed)
    assert all(item.citation and item.rule and item.inputs for item in listed)
    assert [entry.rule_id for entry in rule_trace(report)] == RULE_IDS
    assert not any("Rekomendacji," in text for text in texts(report) if "nie wyznacza" in text)
