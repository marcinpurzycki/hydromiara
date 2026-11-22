"""Source timings: measuring on the recorded sources and the summary statistics."""

import asyncio
from datetime import UTC, date, datetime

import pytest

from tests.tool_helpers import KNOWN_ID, TWO_ROWS, analyse, local_service, test_run

from analysis_tools import source_timing as timing  # isort: skip
from analysis_tools import timing_stats  # isort: skip
from analysis_tools.inputs import InputRow, parse_input  # isort: skip
from analysis_tools.service import HTTP, Service  # isort: skip
from analysis_tools.tables import text  # isort: skip

TODAY = date(2026, 11, 21)
SOURCES = ("parcel", "weather", "soil", "terrain", "satellite", "drought_background")
STARTED = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)


def first_row() -> InputRow:
    return parse_input(TWO_ROWS, today=TODAY)[0][0]


def test_known_numbers():
    spread = timing_stats.distribution([4.0, 1.0, 3.0, 2.0, 10.0, 6.0, 5.0, 9.0, 8.0, 7.0])
    assert (spread.count, spread.minimum, spread.maximum) == (10, 1.0, 10.0)
    assert spread.median == 5.5
    assert spread.p90 == 9.0
    assert timing_stats.percentile([5.0, 1.0, 3.0], 0.9) == 5.0
    assert timing_stats.percentile([2.5], 0.9) == 2.5
    assert timing_stats.percentile(list(range(1, 21)), 0.9) == 18
    assert timing_stats.distribution([]) is None
    assert timing_stats.distribution([7.0]).median == 7.0
    assert timing_stats.share_pct(3, 4) == 75.0
    assert timing_stats.share_pct(1, 3) == 33.3
    assert timing_stats.share_pct(0, 0) is None


def measured(source, duration, *, ok=True, limit=25.0, call="first", phase="isolated") -> dict:
    return {
        "phase": phase, "source": source, "call": call, "ok": text(ok),
        "duration_s": text(duration), "limit_s": text(limit),
        "within_limit": text(ok and duration <= limit),
    }  # fmt: skip


def test_summary_counts_answers_in_time_and_describes_only_calls_with_data():
    rows = [
        measured("soil", 10.0),
        measured("soil", 20.0, call="repeat"),
        measured("soil", 30.0, call="repeat"),
        measured("soil", 25.0, ok=False, call="repeat"),
        measured("analysis_total", 12.0, limit=30.0, phase="analysis"),
        measured("soil", 11.0, phase="analysis"),
    ]
    by_key = {(s["phase"], s["source"], s["call"]): s for s in timing_stats.summarise(rows)}
    overall = by_key[("isolated", "soil", "all")]
    assert (overall["calls"], overall["with_data"], overall["within_limit"]) == (4, 3, 2)
    assert overall["within_limit_pct"] == 50.0
    assert (overall["min_s"], overall["median_s"], overall["p90_s"], overall["max_s"]) == (
        10.0, 20.0, 30.0, 30.0,
    )  # fmt: skip
    assert overall["limit_s"] == "25"
    assert by_key[("isolated", "soil", "first")]["median_s"] == 10.0
    repeat = by_key[("isolated", "soil", "repeat")]
    assert (repeat["calls"], repeat["with_data"], repeat["median_s"]) == (3, 2, 25.0)
    assert ("analysis", "soil", "repeat") not in by_key
    assert set(by_key[("analysis", "analysis_total", "all")]) == set(timing_stats.SUMMARY_COLUMNS)
    # The whole analysis stands before its sources.
    order = [(s["phase"], s["source"]) for s in timing_stats.summarise(rows) if s["call"] == "all"]
    assert order == [("isolated", "soil"), ("analysis", "analysis_total"), ("analysis", "soil")]


def test_source_that_never_gave_data_has_counts_and_no_times():
    summary = timing_stats.summarise([measured("soil", 25.0, ok=False)])[0]
    assert (summary["calls"], summary["with_data"], summary["within_limit_pct"]) == (1, 0, 0.0)
    assert summary["median_s"] is None and summary["p90_s"] is None
    line = timing_stats.markdown([summary]).splitlines()[2]
    assert line == "| isolated | soil | 1 | 0 | 0 (0%) | 25 |  |  |  |  |  |  |"


def test_summary_table_in_markdown():
    rows = [measured("soil", 10.0), measured("soil", 20.5, call="repeat")]
    lines = timing_stats.markdown(timing_stats.summarise(rows)).splitlines()
    assert lines[0] == "| " + " | ".join(timing_stats.MARKDOWN_HEADERS) + " |"
    assert lines[2] == (
        "| isolated | soil | 2 | 2 | 2 (100%) | 25 | 10.00 | 15.25 | 20.50 | 20.50 | 10.00 | 20.50 |"
    )
    assert len(lines) == 3


def test_every_source_is_called_on_its_own_with_its_time_limit(client):
    sources = timing.application_sources()
    timings = asyncio.run(timing.measure_isolated(sources, first_row()))
    assert tuple(t.source for t in timings) == SOURCES
    limits = timing.source_limits(sources)
    assert limits["soil"] == 14.0 and limits["analysis_total"] == 30.0 and "hydro" not in limits
    for item in timings:
        assert item.ok and item.within_limit
        assert item.duration_s >= 0 and item.limit_s == limits[item.source]
        assert item.chain_step == 1 and item.fetched_at is not None
    rows = timing.timing_rows(first_row(), 2, timing.ISOLATED, STARTED, timings, test_run())
    assert all(set(row) == set(timing.COLUMNS) for row in rows)
    assert {row["call"] for row in rows} == {"repeat"}
    assert rows[0]["started_at"] == "2026-11-21T10:00:00Z" and rows[0]["phase"] == "isolated"
    assert (rows[0]["parcel_id"], rows[0]["repeat"], rows[0]["label"]) == (KNOWN_ID, 2, "first")
    assert rows[1]["data_date"] == "2012-09-03/2023-06-20"


def test_without_the_parcel_only_its_call_is_measured(client):
    unknown = InputRow(line=2, parcel_id="999999_9.9999.1", crop_id="winter_wheat",
                       analysis_date=date(2023, 6, 20))  # fmt: skip
    timings = asyncio.run(timing.measure_isolated(timing.application_sources(), unknown))
    assert [t.source for t in timings] == ["parcel"]
    assert not timings[0].ok and timings[0].within_limit is False
    assert "nie istnieje" in timings[0].message


def test_source_that_fails_alone_is_a_call_without_data(client):
    second = parse_input(TWO_ROWS, today=TODAY)[0][1]
    timings = asyncio.run(timing.measure_isolated(timing.application_sources(), second))
    satellite = next(t for t in timings if t.source == "satellite")
    assert not satellite.ok and satellite.within_limit is False and satellite.message
    assert all(t.ok for t in timings if t.source != "satellite")


def test_whole_analysis_gives_its_total_and_the_time_of_every_source(client, reports_db):
    limits = timing.source_limits(timing.application_sources())
    result = analyse(local_service(client, reports_db), [first_row()])[0]
    timings = timing.analysis_timings(result, limits)
    assert tuple(t.source for t in timings) == (timing.ANALYSIS_TOTAL, *SOURCES)
    total = timings[0]
    assert total.ok and total.limit_s == 30.0 and total.within_limit
    assert total.duration_s == pytest.approx(result.total_s, abs=0.001)
    assert all(t.duration_s is not None and t.limit_s == limits[t.source] for t in timings[1:])
    row = timing.timing_rows(first_row(), 1, timing.ANALYSIS, STARTED, timings, test_run())[0]
    assert (row["call"], row["source"], row["ok"]) == ("first", "analysis_total", True)


def test_over_http_only_the_total_time_is_known(client):
    result = analyse(Service(client=client, mode=HTTP), [first_row()])[0]
    timings = timing.analysis_timings(result, {"analysis_total": 30.0, "soil": 25.0})
    assert timings[0].source == timing.ANALYSIS_TOTAL and timings[0].duration_s > 0
    soil = next(t for t in timings if t.source == "soil")
    assert soil.ok and soil.duration_s is None and soil.within_limit is None


def test_failed_analysis_is_a_total_without_data(client, reports_db):
    unknown = InputRow(line=2, parcel_id="999999_9.9999.1", crop_id="winter_wheat",
                       analysis_date=date(2023, 6, 20))  # fmt: skip
    result = analyse(local_service(client, reports_db), [unknown])[0]
    timings = timing.analysis_timings(result, {"analysis_total": 30.0})
    assert len(timings) == 1
    assert not timings[0].ok and timings[0].message.startswith("parcel_unavailable")


def test_calls_without_a_known_time_are_not_judged_against_the_limit():
    unknown = {**measured("soil", 1.0, phase="analysis"), "duration_s": "", "within_limit": ""}
    summary = timing_stats.summarise([unknown])[0]
    assert (summary["calls"], summary["with_data"]) == (1, 1)
    assert summary["within_limit"] is None and summary["within_limit_pct"] is None
    line = timing_stats.markdown([summary]).splitlines()[2]
    assert line == "| analysis | soil | 1 | 1 | not measured | 25 |  |  |  |  |  |  |"
