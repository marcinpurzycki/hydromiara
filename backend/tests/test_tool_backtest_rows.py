"""Backtest rows built from analyses on the recorded sources."""

import time
from datetime import date

import pytest

from tests.tool_helpers import KNOWN_ID, TWO_ROWS, analyse, local_service, no_wait, test_run

from analysis_tools.backtest_rows import COLUMNS, MARKDOWN_HEADERS, markdown, result_row  # isort: skip
from analysis_tools.inputs import InputRow, parse_input  # isort: skip
from analysis_tools.runner import run_analyses  # isort: skip
from analysis_tools.service import HTTP, Service  # isort: skip
from analysis_tools.tables import text  # isort: skip

TODAY = date(2026, 11, 21)


def input_rows(extra: str = "") -> list[InputRow]:
    rows, problems = parse_input(TWO_ROWS + extra, today=TODAY)
    assert problems == []
    return rows


def as_text(row: dict) -> dict[str, str]:
    """The row as it is read back from the output file."""
    return {column: text(row.get(column)) for column in COLUMNS}


@pytest.fixture
def service(client, reports_db) -> Service:
    return local_service(client, reports_db)


def test_column_names_are_fixed():
    assert COLUMNS == (
        "label", "region", "parcel_id", "crop_id", "analysis_date",
        "status", "failure", "total_s", "within_budget", "any_deficit",
        "current_level", "current_label", "current_assessed", "current_confidence",
        "season_state",
        "multiyear_deficit_years", "multiyear_total_years", "multiyear_level",
        "multiyear_confidence", "multiyear_deficit_year_list", "multiyear_year_list",
        "consistency_result", "cdi_dekad", "cdi_class", "cdi_result", "satellite_scene",
        "causes_found", "causes_without_data", "recommendations", "irrigation_justified",
        "water_capacity_source", "available_water_mm", "limitations",
        "sources_answered", "sources_missing",
        "parcel_chain_step", "parcel_s", "parcel_data_date",
        "weather_chain_step", "weather_s", "weather_data_date",
        "soil_chain_step", "soil_s", "soil_data_date",
        "terrain_chain_step", "terrain_s", "terrain_data_date",
        "satellite_chain_step", "satellite_s", "satellite_data_date",
        "hydro_chain_step", "hydro_s", "hydro_data_date",
        "drought_background_chain_step", "drought_background_s", "drought_background_data_date",
        "source_notes", "fetched_at", "started_at", "mode", "host", "code_version",
    )  # fmt: skip
    assert len(set(COLUMNS)) == len(COLUMNS)


def test_row_of_a_finished_analysis(service):
    result = analyse(service, input_rows()[:1])[0]
    report = result.report
    row = result_row(result, test_run())
    assert set(row) <= set(COLUMNS)
    written = as_text(row)
    assert written["label"] == "first" and written["region"] == "Kujawy"
    assert (written["parcel_id"], written["crop_id"]) == (KNOWN_ID, "winter_wheat")
    assert written["analysis_date"] == "2023-06-20"
    assert (written["status"], written["failure"]) == ("done", "")
    assert float(written["total_s"]) > 0 and written["within_budget"] == "true"
    # Both verdicts with their confidence, as the Report states them.
    assert written["current_level"] == str(report.current_status.deficit_level) == "2"
    assert written["current_label"] == report.current_status.label
    assert written["current_assessed"] == "true"
    assert written["current_confidence"] == report.current_status.confidence.level
    multiyear = report.multiyear_susceptibility
    assert written["multiyear_deficit_years"] == str(multiyear.deficit_years) == "9"
    assert written["multiyear_total_years"] == "10"
    assert written["multiyear_level"] == str(multiyear.deficit_level)
    assert written["multiyear_confidence"] == multiyear.confidence.level
    assert written["multiyear_year_list"].split(";")[0] == "2014"
    assert "2017" not in written["multiyear_deficit_year_list"].split(";")
    assert written["any_deficit"] == "true"
    assert written["season_state"] == "in_season"
    # The independent drought indicator and the consistency check.
    assert written["consistency_result"] == report.consistency_check.result == "zgodne"
    assert (written["cdi_dekad"], written["cdi_class"]) == ("2023-06-11", "2")
    assert written["satellite_scene"] == "2023-06-19"
    assert written["causes_found"] == "crop_demand;precipitation"
    assert written["recommendations"].split(";")[0] == "watch_crop_in_critical_period"
    assert written["irrigation_justified"] == "true"
    assert written["water_capacity_source"] == "soil_profile"
    assert written["limitations"] == str(sum(1 for i in report.limitations if not i.permanent))
    # Sources: which answered, from which chain link, in what time, for which dates.
    assert written["sources_answered"] == "parcel;weather;soil;terrain;satellite;drought_background"
    assert written["sources_missing"] == "hydro"
    for topic in ("parcel", "weather", "soil", "terrain", "satellite", "drought_background"):
        assert written[f"{topic}_chain_step"] == "1"
        assert float(written[f"{topic}_s"]) >= 0
    assert written["weather_data_date"] == "2012-09-03/2023-06-20"
    assert written["hydro_chain_step"] == written["hydro_s"] == ""
    assert written["fetched_at"].endswith("Z") and written["started_at"].endswith("Z")
    assert written["mode"] == "in_process" and written["code_version"] and written["host"]


def test_source_without_data_is_listed_with_its_reason(service):
    # The recorded scene catalogue answers only for the first date.
    result = analyse(service, input_rows()[1:2])[0]
    written = as_text(result_row(result, test_run()))
    assert written["status"] == "done"
    assert written["sources_missing"] == "satellite;hydro"
    assert "satellite" not in written["sources_answered"]
    assert written["satellite_chain_step"] == ""
    assert float(written["satellite_s"]) >= 0
    assert written["source_notes"].startswith("satellite: ")
    assert written["satellite_scene"] == ""


def test_failed_analysis_gives_a_row_with_the_reason(service):
    rows = input_rows("999999_9.9999.1,winter_wheat,2023-06-20,missing parcel,\n")
    results = analyse(service, rows)
    assert [result.state for result in results] == ["done", "done", "failed"]
    written = as_text(result_row(results[2], test_run()))
    assert written["status"] == "failed"
    assert written["failure"].startswith("parcel_unavailable: ")
    assert written["label"] == "missing parcel"
    assert written["total_s"] != "" and written["started_at"] != ""
    for column in ("current_level", "multiyear_deficit_years", "consistency_result", "any_deficit"):
        assert written[column] == ""


def test_request_the_service_refuses_gives_a_row_with_the_reason(service):
    refused = InputRow(line=2, parcel_id=KNOWN_ID, crop_id="sunflower", analysis_date=TODAY)
    result = analyse(service, [refused])[0]
    written = as_text(result_row(result, test_run()))
    assert written["status"] == "failed"
    assert written["failure"].startswith("not_accepted: unknown_crop: ")
    assert written["total_s"] == ""


def test_verdict_that_is_not_assessed_has_no_deficit_level(service):
    rows = input_rows(f"{KNOWN_ID},bare_field,2023-06-20,,\n")
    written = as_text(result_row(analyse(service, rows[2:])[0], test_run()))
    assert written["status"] == "done"
    assert written["current_assessed"] == "false"
    assert written["current_level"] == "" and written["multiyear_level"] == ""
    assert written["multiyear_deficit_years"] == "" and written["multiyear_total_years"] == "0"
    assert written["any_deficit"] == ""
    assert written["consistency_result"] == "brak danych"


def test_over_http_times_are_empty_and_reasons_come_from_the_status(client):
    remote = Service(client=client, mode=HTTP, store=None)
    result = analyse(remote, input_rows()[1:2])[0]
    assert result.outcomes == []
    written = as_text(result_row(result, test_run()))
    assert written["status"] == "done" and written["current_level"] == "2"
    assert written["sources_missing"] == "satellite;hydro"
    assert written["weather_chain_step"] == "1" and written["weather_s"] == ""
    assert "satellite: " in written["source_notes"]


def test_same_input_gives_the_same_verdicts(service):
    first, second = (as_text(result_row(r, test_run())) for r in analyse(service, input_rows()[:1] * 2))
    changing = {"total_s", "fetched_at", "started_at", "parcel_data_date"}
    changing |= {column for column in COLUMNS if column.endswith("_s")}
    assert {c: v for c, v in first.items() if c not in changing} == {
        c: v for c, v in second.items() if c not in changing
    }


def test_markdown_table_has_one_line_per_analysis(service):
    rows = input_rows("999999_9.9999.1,winter_wheat,2023-06-20,missing parcel,\n")
    written = [as_text(result_row(result, test_run())) for result in analyse(service, rows)]
    lines = markdown(written).splitlines()
    assert lines[0] == "| " + " | ".join(MARKDOWN_HEADERS) + " |"
    assert lines[1] == "|" + "|".join(["---"] * len(MARKDOWN_HEADERS)) + "|"
    assert len(lines) == 5
    assert all(line.count("|") == len(MARKDOWN_HEADERS) + 1 for line in lines)
    cells = [cell.strip() for cell in lines[2].strip("|").split("|")]
    assert cells[:4] == ["first", KNOWN_ID, "winter_wheat", "2023-06-20"]
    assert cells[4:10] == ["wyraźny niedobór", "wysoka", "9 of 10", "niska", "2 (2023-06-11)", "zgodne"]
    assert cells[10:12] == ["crop_demand, precipitation", "hydro"]
    assert "analysis failed: parcel_unavailable" in lines[4]


def test_several_analyses_can_run_at_once(service, weather):
    weather.hold = True
    seen: list[int] = []

    def release_when_both_wait(seconds: float) -> None:
        time.sleep(seconds)
        seen.append(len(weather.requests))
        if len(weather.requests) == 2:
            weather.hold = False

    results = list(
        run_analyses(
            service, input_rows(), no_wait(), concurrency=2, poll_s=0.01,
            announce=lambda _: None, sleep=release_when_both_wait,
        )  # fmt: skip
    )
    # Both analyses were waiting for the weather before either could end.
    assert 2 in seen
    assert sorted(result.row.label for result in results) == ["first", "second"]
    assert all(result.done for result in results)
