"""Output of the command line tools: the growing CSV file, pacing, Markdown tables."""

import json
from datetime import UTC, datetime, timedelta

import pytest

import tests.tool_helpers  # noqa: F401  (puts the tools on the import path)

from analysis_tools import pacing  # isort: skip
from analysis_tools.pacing import DailyAllowanceUsed, Pace  # isort: skip
from analysis_tools.tables import (  # isort: skip
    OutputFileError, ResultFile, append_json_line, csv_text, joined, markdown_table,
    parse_time, text,
)  # fmt: skip

COLUMNS = ("parcel_id", "status", "total_s")


def test_values_have_one_spelling():
    assert [text(v) for v in (None, True, False, 3, 2.0, 1.23456, 0.5, "zgodne")] == [
        "", "true", "false", "3", "2", "1.235", "0.5", "zgodne",
    ]  # fmt: skip
    assert joined([2014, 2015]) == "2014;2015"
    assert joined([]) == ""


def test_rows_are_appended_and_read_back(tmp_path):
    results = ResultFile(tmp_path / "out" / "results.csv", COLUMNS)
    assert results.rows() == []
    results.append([{"parcel_id": "a", "status": "done", "total_s": 1.5, "extra": "ignored"}])
    results.append([{"parcel_id": "b", "status": "failed"}])
    assert results.path.read_text(encoding="utf-8").splitlines() == [
        "parcel_id,status,total_s", "a,done,1.5", "b,failed,",
    ]  # fmt: skip
    assert results.rows() == [
        {"parcel_id": "a", "status": "done", "total_s": "1.5"},
        {"parcel_id": "b", "status": "failed", "total_s": ""},
    ]


def test_file_written_with_other_columns_is_refused(tmp_path):
    path = tmp_path / "results.csv"
    ResultFile(path, ("parcel_id", "status")).append([{"parcel_id": "a", "status": "done"}])
    with pytest.raises(OutputFileError, match="other columns"):
        ResultFile(path, COLUMNS).rows()


def test_rewrite_keeps_only_the_given_rows(tmp_path):
    results = ResultFile(tmp_path / "results.csv", COLUMNS)
    results.append([{"parcel_id": "a", "status": "done"}, {"parcel_id": "b", "status": "failed"}])
    results.rewrite(row for row in results.rows() if row["status"] == "done")
    assert [row["parcel_id"] for row in results.rows()] == ["a"]
    assert not (tmp_path / "results.csv.tmp").exists()
    results.rewrite([])
    assert results.rows() == []
    assert results.path.read_text(encoding="utf-8") == "parcel_id,status,total_s\n"


def test_raw_results_are_one_json_document_per_line(tmp_path):
    path = tmp_path / "raw.jsonl"
    append_json_line(path, {"a": 1, "label": "żyto"})
    append_json_line(path, {"when": datetime(2026, 11, 21, tzinfo=UTC)})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"a": 1, "label": "żyto"}
    assert "żyto" in lines[0]
    assert json.loads(lines[1])["when"].startswith("2026-11-21")


def test_markdown_table_is_a_pipe_table_with_escaped_cells():
    table = markdown_table(("Parcel", "Time [s]"), [("a|b", 1.5), ("two\nlines", None)])
    assert table == (
        "| Parcel | Time [s] |\n|---|---|\n| a\\|b | 1.5 |\n| two lines |  |\n"
    )


def test_csv_text_has_a_header_and_fixed_columns():
    assert csv_text(("a", "b"), [{"a": 1, "b": True, "c": 2}]) == "a,b\n1,true\n"


def test_times_written_by_the_tools_are_read_back():
    assert parse_time("2026-11-21T10:00:05Z") == datetime(2026, 11, 21, 10, 0, 5, tzinfo=UTC)
    assert parse_time("") is None
    assert parse_time("yesterday") is None


class Clock:
    """A clock that moves only when the pace sleeps."""

    def __init__(self) -> None:
        self.now = 1_800_000_000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def moment(self, seconds_ago: float) -> datetime:
        return datetime.fromtimestamp(self.now - seconds_ago, UTC)


def paced(clock: Clock, *arguments, **options) -> Pace:
    return Pace(*arguments, clock=clock, sleep=clock.sleep, **options)


def test_starts_are_spaced():
    clock = Clock()
    pace = paced(clock, 13.0, 0, 0)
    pace.acquire()
    assert clock.slept == []
    clock.now += 4.0
    assert pace.wait_s() == pytest.approx(9.0)
    pace.acquire()
    assert sum(clock.slept) == pytest.approx(9.0)
    clock.now += 20.0
    assert pace.wait_s() == 0.0


def test_hourly_cap_waits_until_the_oldest_start_is_an_hour_old():
    clock = Clock()
    said: list[str] = []
    pace = paced(clock, 0.0, 2, 0, earlier=[clock.moment(3000), clock.moment(100)])
    assert pace.wait_s() == pytest.approx(600.0)
    pace.acquire(said.append)
    assert sum(clock.slept) == pytest.approx(600.0)
    assert max(clock.slept) <= 5.0
    assert len(said) == 1 and "hourly allowance" in said[0]
    # Now the start made 700 s ago has to become an hour old.
    assert pace.wait_s() == pytest.approx(2900.0)


def test_daily_cap_stops_the_run_and_says_when_to_continue():
    clock = Clock()
    earlier = [clock.moment(80_000), clock.moment(50), clock.moment(90_000)]
    pace = paced(clock, 0.0, 0, 2, earlier=earlier)
    with pytest.raises(DailyAllowanceUsed) as stop:
        pace.acquire()
    # The start made 25 hours ago no longer counts; the one 80 000 s ago has to pass.
    assert stop.value.again_at == pytest.approx(clock.now + 6400.0)
    assert clock.slept == []


def test_zero_means_no_cap():
    clock = Clock()
    pace = paced(clock, 0.0, 0, 0, earlier=[clock.moment(10)] * 500)
    for _ in range(50):
        pace.acquire()
    assert clock.slept == []


def test_default_pace_stays_within_the_published_limits():
    # Soil service: 5 calls per minute; one call per start.
    assert 60.0 / pacing.DEFAULT_SPACING_S < 5
    # Weather archive: 5 000 per hour and 10 000 per day at a cost of about 88 per start.
    assert pacing.DEFAULT_PER_HOUR * 88 <= 5_000
    assert pacing.DEFAULT_PER_DAY * 88 <= 10_000
    # Parcel service: 40 calls per minute at night, 10 000 per day.
    assert 60.0 / pacing.DEFAULT_SPACING_S < 40
    assert timedelta(seconds=pacing.DAY_S) == timedelta(days=1)
