"""Report assembly: valid against the contract, repeatable, honest about what is missing."""

import json

from app.catalog.crops import get_crop
from app.contracts.report import Limitation, Report
from app.engine.limitations import PERMANENT_LIMITATIONS
from app.engine.soil_limitations import NO_SOIL_TEXT
from app.mock import data as mock_data
from app.orchestrator import report_pending as pending
from app.orchestrator.report_builder import ReportInputs, build_report
from app.orchestrator.report_verdicts import NOT_ASSESSED_LABEL
from tests.analysis_helpers import ANALYSIS_DATE, NOW, stored_source_data
from tests.engine_helpers import recorded_soil
from tests.limitation_helpers import complete_source_data


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
    assert report.season.last_season.start.isoformat() == "2022-10-05"
    rule_ids = [entry.rule_id for entry in report.trace]
    assert rule_ids[:3] == [
        "root_zone.capacity", "current_status.level", "multiyear.deficit_years",
    ]
    assert rule_ids[3] == "season.state"
    assert rule_ids[-1] == "consistency_check.result"
    assert report.map.parcel_geometry == stored_source_data().parcel.geometry
    assert [source.topic for source in report.sources] == ["parcel", "weather"]
    assert not any(source.missing for source in report.sources)


def test_parts_without_a_module_are_marked_as_not_assessed():
    report = build()
    assert report.historical_course is None
    assert any(cause.recommendations for cause in report.causes)
    # The summary is the template one, made from this Report; nothing is pending in it.
    assert report.summary.source == "template"
    assert report.headline in report.summary.text
    assert not any("nie wyznacza jeszcze" in text for text in texts(report))
    assert report.current_status.reason == pending.REASON_PENDING
    assert report.multiyear_susceptibility.typical_period is None
    assert report.map.retention_sites == [] and report.map.water_objects == []


def test_nothing_is_copied_from_the_placeholder_report():
    mock = mock_data.report_for("r1")
    report = build()
    assert report.summary.text != mock.summary.text
    assert report.irrigation.text != mock.irrigation.text
    assert report.current_status.reason != mock.current_status.reason
    # Only a permanent limitation may read the same: it is a fixed sentence.
    shared = {limitation.text for limitation in mock.limitations} & set(texts(report))
    assert shared <= {limitation.text for limitation in PERMANENT_LIMITATIONS}


def test_missing_soil_is_a_limitation():
    report = build()
    assert report.trace[0].values["capacity_source"] == "fallback"
    assert texts(report).count(NO_SOIL_TEXT) == 1
    assert report.trace[0].values["available_water_mm_per_m"] == 150
    with_soil = build(source_data=stored_source_data().model_copy(update={"soil": recorded_soil()}))
    assert NO_SOIL_TEXT not in texts(with_soil)
    assert with_soil.trace[0].values["capacity_source"] == "iung_category"


def test_source_limitations_are_kept_and_absent_data_are_named():
    limitation = Limitation(
        text="Brak zgłoszony przez źródło.", affects="multiyear", permanent=False
    )
    report = build(source_limitations=(limitation, limitation))
    assert report.limitations.count(limitation) == 1
    for start in (
        "Brak danych o ukształtowaniu terenu", "Brak danych o ciekach, rowach i zbiornikach",
        "Brak odczytów satelitarnych", "Brak niezależnego wskaźnika suszy",
    ):
        assert sum(text.startswith(start) for text in texts(report)) == 1
    assert "Brak zgłoszony przez źródło" in report.multiyear_susceptibility.confidence.why
    assert "Brak zgłoszony przez źródło" not in report.current_status.confidence.why


def test_permanent_limitations_close_every_report():
    for report in (build(), build("bare_field"), build(source_data=complete_source_data())):
        assert tuple(report.limitations[-len(PERMANENT_LIMITATIONS):]) == PERMANENT_LIMITATIONS
        assert len(set(texts(report))) == len(report.limitations)


def test_confidence_follows_the_limitations_of_each_verdict():
    # Weather only, as the analysis runs today: stand-in capacity, no comparison data.
    report = build()
    current = report.current_status.confidence
    multiyear = report.multiyear_susceptibility.confidence
    assert (current.level, multiyear.level) == ("niska", "niska")
    assert "przyjęto przeciętną zdolność gleby" in current.why
    assert "przyjęto przeciętną zdolność gleby" in multiyear.why
    assert "wskaźnika suszy" in current.why and "wskaźnika suszy" not in multiyear.why

    report = build(source_data=complete_source_data())
    assert Report.model_validate_json(report.model_dump_json()) == report
    for verdict in (report.current_status, report.multiyear_susceptibility):
        assert verdict.confidence.level == "wysoka"
    own = [limitation for limitation in report.limitations if not limitation.permanent]
    # The stand-in terrain grid of the helper is in a system that is not read, which the
    # Report says.
    # No recommendation that needs the terrain answers a cause found here (only the
    # crop demand is), so none is named as not checked.
    assert len(own) == 1
    assert own[0].affects == "recommendations" and "ukształtowaniu terenu" in own[0].text


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
    assert NOT_ASSESSED_LABEL in texts(report)[0] and "Pola bez uprawy" in texts(report)[0]
    for verdict in (current, multiyear):
        assert verdict.confidence.level == "niska"
        assert "Pola bez uprawy" in verdict.confidence.why
    assert not report.season.in_season and report.season.last_season is None
    assert not report.irrigation.applicable
    assert json.loads(report.model_dump_json())["trace"][1]["result"] == NOT_ASSESSED_LABEL
