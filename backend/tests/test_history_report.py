"""The crop history in the Report: a course next to the verdicts, nothing else changes."""

import pytest

from app.catalog.crops import get_crop
from app.contracts.analyses import CropHistory
from app.contracts.report import Report
from app.orchestrator.report_builder import ReportInputs, build_report
from app.summary.facts import first_sentence
from tests.analysis_helpers import ANALYSIS_DATE, NOW
from tests.history_helpers import SAME, WINDOW, data, years
from tests.limitation_helpers import complete_source_data

HISTORIES = [
    SAME,
    years(y2015="bare_field", y2016="bare_field"),
    CropHistory(years=dict.fromkeys(WINDOW, "bare_field")),
    years(y2019="winter_wheat"),
]
# Parts of the Report a crop history must never change.
UNTOUCHED = (
    "headline", "season", "current_status", "causes", "irrigation",
    "consistency_check", "sources", "limitations", "map",
)


def build(history: CropHistory | None = None, crop_id: str = "winter_wheat", **changes) -> Report:
    inputs = ReportInputs(
        report_id="r1",
        created_at=NOW,
        source_data=changes.pop("source_data", data()),
        crop=get_crop(crop_id),
        analysis_date=ANALYSIS_DATE,
        crop_history=history,
        **changes,
    )
    return build_report(inputs)


def test_without_a_history_there_is_no_course():
    report = build()
    assert report.historical_course is None
    assert "Historii upraw nie podano" in report.multiyear_susceptibility.history_assumption
    assert "crop_history.course" not in [entry.rule_id for entry in report.trace]


@pytest.mark.parametrize("history", HISTORIES)
@pytest.mark.parametrize("source", [data, complete_source_data], ids=["soil", "all_sources"])
def test_history_changes_nothing_but_the_course_and_the_assumption(history, source):
    plain = build(source_data=source())
    given = build(history, source_data=source())
    for part in UNTOUCHED:
        assert getattr(given, part) == getattr(plain, part), part
    # The susceptibility: number of years, level, the list of years, confidence.
    before, after = plain.multiyear_susceptibility, given.multiyear_susceptibility
    unchanged = before.model_dump(exclude={"history_assumption"})
    assert after.model_dump(exclude={"history_assumption"}) == unchanged
    assert (after.deficit_years, after.total_years, after.deficit_level) == (
        before.deficit_years, before.total_years, before.deficit_level,
    )
    assert after.years == before.years and after.confidence == before.confidence
    assert after.history_assumption != before.history_assumption
    # Causes carry the recommendations; the trace only gains the entry of the course.
    assert [cause.recommendations for cause in given.causes] == [
        cause.recommendations for cause in plain.causes
    ]
    assert given.trace[:-1] == plain.trace
    assert given.trace[-1].rule_id == "crop_history.course"
    assert given.historical_course is not None and plain.historical_course is None
    # The summary only gains the sentence that compares the course with the susceptibility.
    sentence = first_sentence(given.historical_course.comparison_sentence)
    assert sentence in given.summary.text
    assert given.summary.text.replace(f" {sentence}", "") == plain.summary.text


def test_course_in_the_report_follows_the_contract():
    report = build(years(y2015="bare_field", y2016="bare_field"))
    course = report.historical_course
    assert [year.year for year in course.years] == list(WINDOW)
    assert [year.crop.id for year in course.years if year.year in (2015, 2016)] == [
        "bare_field", "bare_field",
    ]
    assert all(year.satellite_note for year in course.years)
    assert "w 8 z 8 ocenionych lat" in course.comparison_sentence
    assert "w latach 2015, 2016" in report.multiyear_susceptibility.history_assumption
    assert Report.model_validate_json(report.model_dump_json()) == report
    assert build(years(y2015="bare_field", y2016="bare_field")) == report


def test_confirmed_same_crop_gives_a_course_equal_to_the_susceptibility():
    report = build(SAME)
    multiyear = report.multiyear_susceptibility
    assert [(year.year, year.deficit) for year in report.historical_course.years] == [
        (year.year, year.deficit) for year in multiyear.years
    ]
    assert {year.crop.id for year in report.historical_course.years} == {"winter_wheat"}
    assert "to potwierdza" in multiyear.history_assumption


def test_field_without_a_crop_ignores_a_history():
    plain, given = build(crop_id="bare_field"), build(SAME, crop_id="bare_field")
    assert given == plain and given.historical_course is None


def test_derived_report_names_its_source():
    report = build(SAME, derived_from="source-id")
    assert report.meta.derived_from == "source-id"
    assert build(SAME).meta.derived_from is None
