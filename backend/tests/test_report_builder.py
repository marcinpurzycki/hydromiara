"""Report assembly: valid against the contract, repeatable, honest about what is missing."""

import json

from app.catalog.crops import get_crop
from app.contracts.report import Report
from app.mock import data as mock_data
from app.orchestrator import report_pending as pending
from app.orchestrator.report_builder import ReportInputs, build_report
from app.orchestrator.report_verdicts import NOT_ASSESSED_LABEL
from tests.analysis_helpers import ANALYSIS_DATE, NOW, stored_source_data
from tests.engine_helpers import recorded_soil


def build(crop_id: str = "winter_wheat", **changes) -> Report:
    inputs = ReportInputs(
        report_id="r1",
        created_at=NOW,
        source_data=changes.pop("source_data", stored_source_data()),
        crop=get_crop(crop_id),
        analysis_date=ANALYSIS_DATE,
        **changes,
    )
    return build_report(inputs)


def texts(report: Report) -> list[str]:
    return [limitation.text for limitation in report.limitations]


def test_report_round_trips_through_the_contract():
    report = build()
    assert Report.model_validate_json(report.model_dump_json()) == report


def test_same_inputs_give_the_same_report():
    assert build().model_dump_json() == build().model_dump_json()


def test_verdicts_come_from_the_engine():
    report = build()
    assert report.meta.crop.id == "winter_wheat"
    assert report.meta.analysis_date == ANALYSIS_DATE
    assert report.meta.derived_from is None and report.meta.changed_from_date is None
    current, multiyear = report.current_status, report.multiyear_susceptibility
    assert current.deficit_level in range(4)
    assert current.details["assessed"] is True
    assert current.details["state_date"] == ANALYSIS_DATE.isoformat()
    assert multiyear.total_years == len(multiyear.years) == 10
    assert multiyear.deficit_years == sum(year.deficit for year in multiyear.years)
    assert multiyear.years[-1].partial and multiyear.years[-1].year == 2023
    assert f"{multiyear.deficit_years} z 10 lat" in report.headline
    assert current.label in report.headline
    assert report.season.in_season
    assert report.season.last_season.start.isoformat() == "2022-09-25"
    assert [entry.rule_id for entry in report.trace] == [
        "root_zone.capacity", "current_status.level", "multiyear.deficit_years",
    ]
    assert report.map.parcel_geometry == stored_source_data().parcel.geometry
    assert [source.topic for source in report.sources] == ["parcel", "weather"]
    assert not any(source.missing for source in report.sources)


def test_parts_without_a_module_are_marked_as_not_assessed():
    report = build()
    assert report.causes == [] and report.historical_course is None
    assert report.consistency_check.result == "brak danych"
    assert report.consistency_check.items == []
    assert report.irrigation.justified is None and report.irrigation.amount_mm is None
    assert report.summary.source == "template"
    assert report.current_status.reason == pending.REASON_PENDING
    assert report.multiyear_susceptibility.typical_period is None
    for verdict in (report.current_status, report.multiyear_susceptibility):
        assert verdict.confidence == pending.pending_confidence()
    assert pending.pending_limitation() in report.limitations
    assert report.map.retention_sites == [] and report.map.downhill_direction is None


def test_nothing_is_copied_from_the_placeholder_report():
    mock = mock_data.report_for("r1")
    report = build()
    assert report.summary.text != mock.summary.text
    assert report.irrigation.text != mock.irrigation.text
    assert report.current_status.reason != mock.current_status.reason
    assert not {limitation.text for limitation in mock.limitations} & set(texts(report))


def test_missing_soil_is_a_limitation():
    report = build()
    assert report.trace[0].values["capacity_source"] == "fallback"
    assert any("Brak danych o glebie" in text and "150 mm" in text for text in texts(report))
    with_soil = build(source_data=stored_source_data().model_copy(update={"soil": recorded_soil()}))
    assert not any("Brak danych o glebie" in text for text in texts(with_soil))
    assert with_soil.trace[0].values["capacity_source"] == "soil_profile"


def test_source_limitations_are_kept_and_absent_data_are_named():
    limitation = mock_data.report_for("r1").limitations[0]
    report = build(source_limitations=(limitation,))
    assert report.limitations[0] == limitation
    absent = next(text for text in texts(report) if text.startswith("Analiza nie korzysta"))
    for label in ("ukształtowanie terenu", "cieki", "satelitarne", "wskaźnik suszy"):
        assert label in absent


def test_field_without_a_crop_is_not_assessed_and_says_so():
    report = build("bare_field")
    current, multiyear = report.current_status, report.multiyear_susceptibility
    assert (current.deficit_level, current.label) == (0, NOT_ASSESSED_LABEL)
    assert current.details["assessed"] is False
    assert current.details["not_assessed_reason"] == "no_crop"
    assert current.details["depletion_mm"] is not None
    assert (multiyear.deficit_level, multiyear.total_years, multiyear.years) == (0, 0, [])
    assert report.headline.count(NOT_ASSESSED_LABEL) == 2
    assert "w normie" not in report.headline
    assert any(NOT_ASSESSED_LABEL in text and "Pola bez uprawy" in text for text in texts(report))
    assert not report.season.in_season and report.season.last_season is None
    assert not report.irrigation.applicable
    assert json.loads(report.model_dump_json())["trace"][1]["result"] == NOT_ASSESSED_LABEL
