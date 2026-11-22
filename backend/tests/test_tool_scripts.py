"""Whole runs of both command line tools on the recorded sources, without network."""

import csv
import json
import os

import pytest

from app.storage.params import DB_PATH_ENV
from tests.tool_helpers import HEADER, KNOWN_ID, TWO_ROWS

import backtest  # isort: skip
import measure_sources  # isort: skip
from analysis_tools import backtest_rows, source_timing, timing_stats  # isort: skip

FAST = ["--spacing", "0", "--max-per-hour", "0", "--max-per-day", "0"]
SOURCES = ("parcel", "weather", "soil", "terrain", "satellite", "drought_background")


@pytest.fixture
def files(tmp_path):
    """Paths of one run: input with two rows, output, Markdown, raw results."""
    source = tmp_path / "input.csv"
    source.write_text(TWO_ROWS, encoding="utf-8")
    return {
        "input": source,
        "output": tmp_path / "out" / "results.csv",
        "markdown": tmp_path / "out" / "table.md",
        "raw": tmp_path / "out" / "raw.jsonl",
    }


def read(path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run_backtest(files, *extra: str) -> int:
    return backtest.main([str(files["input"]), "--output", str(files["output"]), *FAST, *extra])


def run_timing(files, *extra: str) -> int:
    return measure_sources.main(
        [str(files["input"]), "--output", str(files["output"]), *FAST, *extra]
    )


def test_backtest_writes_a_row_per_analysis_and_prints_the_table(files, weather, capsys):
    database = os.environ[DB_PATH_ENV]
    status = run_backtest(files, "--markdown", str(files["markdown"]), "--raw", str(files["raw"]))
    assert status == 0
    rows = read(files["output"])
    assert tuple(rows[0]) == backtest_rows.COLUMNS
    assert [(row["label"], row["analysis_date"], row["status"]) for row in rows] == [
        ("first", "2023-06-20", "done"), ("second", "2023-06-10", "done"),
    ]  # fmt: skip
    assert [row["current_label"] for row in rows] == ["silny niedobór", "wyraźny niedobór"]
    assert [row["cdi_class"] for row in rows] == ["2", "1"]
    assert all(row["mode"] == "in_process" and float(row["weather_s"]) >= 0 for row in rows)
    assert len(weather.requests) == 2
    printed = capsys.readouterr()
    table = printed.out
    assert table.startswith("Tool: backtest; run started ")
    assert "Parameters: input " in table and "spacing_s 0.0" in table
    assert "Rows measured " in table and "mode in_process." in table
    assert table.count("\n| ") == 3 and f"| first | {KNOWN_ID} | winter_wheat | 2023-06-20 |" in table
    assert files["markdown"].read_text(encoding="utf-8") == table
    assert "2 usable input rows, 0 skipped; 0 already in" in printed.err
    raw = [json.loads(line) for line in files["raw"].read_text(encoding="utf-8").splitlines()]
    assert len(raw) == 2
    assert raw[0]["run"]["tool"] == "backtest" and raw[0]["run"]["parameters"]["spacing_s"] == 0.0
    assert raw[0]["report"]["meta"]["parcel"]["parcel_id"] == KNOWN_ID
    assert raw[0]["status"]["state"] == "done"
    assert [o["topic"] for o in raw[0]["source_outcomes"]] == list(SOURCES)
    # The tool used its own temporary database and left the environment as it was.
    assert os.environ[DB_PATH_ENV] == database
    assert not os.path.exists(database) or os.path.getsize(database) == 0


def test_backtest_continues_from_the_output_file(files, weather, capsys):
    files["input"].write_text(TWO_ROWS.splitlines(keepends=True)[0] + TWO_ROWS.splitlines()[1] + "\n")
    assert run_backtest(files) == 0
    assert len(weather.requests) == 1
    files["input"].write_text(TWO_ROWS, encoding="utf-8")
    capsys.readouterr()
    assert run_backtest(files, "--format", "csv") == 0
    # Only the row that was not in the output file was analysed.
    assert len(weather.requests) == 2
    printed = capsys.readouterr()
    assert "1 already in" in printed.err and "1 to run" in printed.err
    assert [row["label"] for row in read(files["output"])] == ["first", "second"]
    shown = list(csv.DictReader(printed.out.splitlines()))
    assert [row["label"] for row in shown] == ["first", "second"]
    assert run_backtest(files, "--format", "none") == 0
    assert len(weather.requests) == 2
    assert capsys.readouterr().out == ""


def test_bad_rows_and_failed_analyses_do_not_stop_the_run(files, weather, capsys):
    files["input"].write_text(
        HEADER
        + "999999_9.9999.1,winter_wheat,2023-06-20,missing parcel,\n"
        + f"{KNOWN_ID},sunflower,2023-06-20,unknown crop,\n"
        + f"{KNOWN_ID},winter_wheat,2023-06-20,first,\n",
        encoding="utf-8",
    )
    assert run_backtest(files) == 1
    printed = capsys.readouterr()
    assert "line 3: crop_id 'sunflower' is not in the crop catalogue" in printed.err
    assert "(available: winter_wheat, winter_rye, " in printed.err and "bare_field)" in printed.err
    rows = read(files["output"])
    assert [(row["label"], row["status"]) for row in rows] == [
        ("missing parcel", "failed"), ("first", "done"),
    ]  # fmt: skip
    assert rows[0]["failure"].startswith("parcel_unavailable: ")
    assert "analysis failed: parcel_unavailable" in printed.out
    # A failed row is kept on the next run and run again only when asked to.
    assert run_backtest(files) == 1
    assert len(weather.requests) == 1
    assert run_backtest(files, "--retry-failed") == 1
    rows = read(files["output"])
    assert [(row["label"], row["status"]) for row in rows] == [
        ("first", "done"), ("missing parcel", "failed"),
    ]  # fmt: skip
    assert len(weather.requests) == 1


def test_unusable_files_end_with_a_message(files, tmp_path, capsys):
    assert backtest.main([str(tmp_path / "absent.csv"), "--output", str(files["output"])]) == 2
    assert "cannot read the input file" in capsys.readouterr().err
    files["input"].write_text("parcel,crop\n", encoding="utf-8")
    assert run_backtest(files) == 2
    assert "lacks the column(s) parcel_id, crop_id, analysis_date" in capsys.readouterr().err
    files["input"].write_text(HEADER, encoding="utf-8")
    assert run_backtest(files) == 2
    assert "no usable rows" in capsys.readouterr().err
    files["input"].write_text(TWO_ROWS, encoding="utf-8")
    files["output"].parent.mkdir(parents=True)
    files["output"].write_text("a,b\n1,2\n", encoding="utf-8")
    assert run_backtest(files) == 2
    assert "other columns" in capsys.readouterr().err
    assert run_timing(files) == 2


def test_backtest_stops_at_the_daily_cap_and_keeps_what_it_has(files, weather, capsys):
    arguments = [str(files["input"]), "--output", str(files["output"]), "--spacing", "0"]
    assert backtest.main([*arguments, "--max-per-day", "1"]) == 3
    assert "daily allowance used (1 starts in 24 hours)" in capsys.readouterr().err
    assert [row["label"] for row in read(files["output"])] == ["first"]
    # The start recorded in the output file still counts on the next run.
    assert backtest.main([*arguments, "--max-per-day", "1"]) == 3
    assert len(weather.requests) == 1
    assert backtest.main([*arguments, "--max-per-day", "2"]) == 0
    assert [row["label"] for row in read(files["output"])] == ["first", "second"]


def test_timing_measures_every_source_alone_and_in_the_analysis(files, weather, capsys):
    status = run_timing(files, "--repeats", "2", "--raw", str(files["raw"]))
    assert status == 0
    rows = read(files["output"])
    assert tuple(rows[0]) == source_timing.COLUMNS
    rounds = {(row["analysis_date"], row["repeat"], row["phase"]) for row in rows}
    assert len(rounds) == 2 * 2 * 2
    first = [row for row in rows if row["analysis_date"] == "2023-06-20"]
    assert [row["source"] for row in first if (row["repeat"], row["phase"]) == ("1", "isolated")] == list(SOURCES)
    assert [row["source"] for row in first if (row["repeat"], row["phase"]) == ("2", "analysis")] == [
        "analysis_total", *SOURCES,
    ]  # fmt: skip
    assert {row["call"] for row in rows if row["repeat"] == "1"} == {"first"}
    assert {row["call"] for row in rows if row["repeat"] == "2"} == {"repeat"}
    assert all(row["ok"] == "true" and row["within_limit"] == "true" for row in first)
    # One weather request per round: 2 rows x 2 repeats x (alone + analysis).
    assert len(weather.requests) == 8
    printed = capsys.readouterr()
    assert printed.out.startswith("Tool: measure_sources; run started ")
    assert "repeats 2" in printed.out
    lines = [line for line in printed.out.splitlines() if line.startswith("| ")]
    assert lines[0] == "| " + " | ".join(timing_stats.MARKDOWN_HEADERS) + " |"
    assert [line.split(" | ")[1] for line in lines[1:]] == [*SOURCES, "analysis_total", *SOURCES]
    assert lines[1].startswith("| isolated | parcel | 4 | 4 | 4 (100%) | 8 | ")
    assert next(line for line in lines if "| analysis | satellite |" in line).split(" | ")[2:4] == ["4", "2"]
    assert len(files["raw"].read_text(encoding="utf-8").splitlines()) == 8


def test_timing_continues_and_can_skip_a_phase(files, weather, capsys):
    assert run_timing(files, "--repeats", "1", "--no-analysis") == 0
    assert len(weather.requests) == 2
    assert {row["phase"] for row in read(files["output"])} == {"isolated"}
    capsys.readouterr()
    assert run_timing(files, "--repeats", "1", "--format", "csv") == 0
    # The isolated rounds were in the file; only the two analyses ran.
    assert len(weather.requests) == 4
    printed = capsys.readouterr()
    assert "2 rounds already in" in printed.err
    summary = list(csv.DictReader(printed.out.splitlines()))
    assert tuple(summary[0]) == timing_stats.SUMMARY_COLUMNS
    assert {(row["phase"], row["call"]) for row in summary} == {
        ("isolated", "all"), ("isolated", "first"), ("analysis", "all"), ("analysis", "first"),
    }  # fmt: skip
    assert run_timing(files, "--repeats", "1", "--format", "none") == 0
    assert len(weather.requests) == 4


def test_timing_reports_a_failed_analysis(files, capsys):
    files["input"].write_text(HEADER + "999999_9.9999.1,winter_wheat,2023-06-20,,\n", encoding="utf-8")
    assert run_timing(files, "--repeats", "1") == 1
    rows = read(files["output"])
    assert [(row["phase"], row["source"], row["ok"]) for row in rows] == [
        ("isolated", "parcel", "false"), ("analysis", "analysis_total", "false"),
    ]  # fmt: skip
    assert rows[1]["message"].startswith("parcel_unavailable: ")
