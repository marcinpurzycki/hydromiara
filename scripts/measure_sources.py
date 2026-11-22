#!/usr/bin/env python3
"""Source timing: how long every data source takes, alone and inside an analysis.

For every row of the input file and every repeat the tool does two rounds.
In the `isolated` round it calls the parcel service and then every connected
source alone, one after another, with the application's adapters and time
limits. In the `analysis` round it runs an ordinary whole analysis, where the
sources work in parallel, and records its total time and the time of every
source in it. The first repeat of a row is a `first` call, later repeats are
`repeat` calls, which shows the difference between a cold and a warm call.

Input: the same CSV file as for scripts/backtest.py (`parcel_id,crop_id,
analysis_date` and optionally `label,region`).

Output: the CSV file given by --output (default source-timings.csv), one row
per measured call, written after every round; running the same command again
continues an interrupted run. At the end a summary per source is printed as a
Markdown table: calls, calls with data, calls with data within the time limit,
and minimum, median, 90th percentile and maximum of the calls with data.
With --format csv the summary is printed as CSV. Result files are not meant
to be committed.

Run from the repository root with the backend's Python environment:

    EDO_DATA_PATH=/path/to/drought/files backend/.venv/bin/python scripts/measure_sources.py \\
        scripts/examples/input_format_example.csv --repeats 3

On the target server, inside the service image (no change of the image):

    docker compose run --rm --no-deps -u "$(id -u)" -e PROBE_HOST="$(hostname)" \\
        -e CODE_VERSION="$(git rev-parse --short HEAD)" \\
        -v "$PWD/scripts:/srv/scripts:ro" -v "$PWD/results:/results" api \\
        python scripts/measure_sources.py scripts/examples/input_format_example.csv \\
        --output /results/source-timings.csv

With --base-url the whole analyses go to a running service over HTTP (their
source times are then not available); the isolated round still calls the
sources from the machine the tool runs on.

Pace: every round is one start (one call to each source), 13 s apart, at most
50 per hour and 100 per day; rows x repeats x 2 rounds have to fit, or the
tool waits for the next hour. See scripts/analysis_tools/pacing.py. Exit
status: 0 done, 1 an analysis failed or input rows were skipped, 2 input or
output file unusable, 3 stopped at the daily cap (run again later).
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis_tools import cli, timing_stats  # noqa: E402
from analysis_tools import source_timing as timing  # noqa: E402
from analysis_tools.inputs import InputFileError, InputRow  # noqa: E402
from analysis_tools.pacing import DailyAllowanceUsed, Pace  # noqa: E402
from analysis_tools.runner import run_analyses  # noqa: E402
from analysis_tools.service import HTTP, IN_PROCESS, RunInfo, new_run, open_service  # noqa: E402
from analysis_tools.tables import OutputFileError, ResultFile, append_json_line  # noqa: E402
from analysis_tools.tables import csv_text  # noqa: E402

DEFAULT_OUTPUT = "source-timings.csv"
DEFAULT_REPEATS = 3


def _unit(row: InputRow, repeat: int, phase: str) -> tuple[str, ...]:
    return (*row.key, str(repeat), phase)


def _record(arguments, results: ResultFile, rows: list[dict], run: RunInfo) -> None:
    results.append(rows)
    if arguments.raw:
        append_json_line(arguments.raw, {"run": run.as_dict(), "measurements": rows})
    brief = ", ".join(
        f"{row['source']} {'-' if row['duration_s'] is None else format(row['duration_s'], '.1f')}"
        f"{'' if row['ok'] else ' (no data)'}"
        for row in rows
    )
    cli.say(f"  {rows[0]['phase']}: {brief}")


def _measure(arguments, rows: list[InputRow], results: ResultFile, done: set, pace: Pace,
             run: RunInfo) -> None:  # fmt: skip
    """All repeats: the isolated rounds of every row, then their whole analyses."""
    with open_service(arguments.base_url, quiet=not arguments.verbose) as service:
        sources = timing.application_sources()
        limits = timing.source_limits(sources)
        with asyncio.Runner() as loop:
            for repeat in range(1, arguments.repeats + 1):
                for row in rows:
                    if arguments.no_isolated or _unit(row, repeat, timing.ISOLATED) in done:
                        continue
                    pace.acquire(cli.say)
                    cli.say(f"repeat {repeat}: sources one by one for {row.name}")
                    started_at = datetime.now(UTC)
                    timings = loop.run(timing.measure_isolated(sources, row))
                    _record(arguments, results, timing.timing_rows(
                        row, repeat, timing.ISOLATED, started_at, timings, run), run)  # fmt: skip
                pending = [
                    row for row in rows
                    if not arguments.no_analysis and _unit(row, repeat, timing.ANALYSIS) not in done
                ]  # fmt: skip
                for result in run_analyses(
                    service, pending, pace, concurrency=arguments.concurrency,
                    announce=lambda text, repeat=repeat: cli.say(f"repeat {repeat}: {text}"),
                ):  # fmt: skip
                    _record(arguments, results, timing.timing_rows(
                        result.row, repeat, timing.ANALYSIS, result.started_at,
                        timing.analysis_timings(result, limits), run), run)  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__, DEFAULT_OUTPUT)
    parser.add_argument(
        "--repeats", type=int, default=DEFAULT_REPEATS,
        help="how many times every row is measured (default: %(default)s)",
    )  # fmt: skip
    parser.add_argument("--no-isolated", action="store_true", help="skip the one-by-one rounds")
    parser.add_argument("--no-analysis", action="store_true", help="skip the whole analyses")
    arguments = parser.parse_args(argv)
    try:
        rows, problems = cli.read_rows(arguments)
        results, existing = cli.open_output(arguments, timing.COLUMNS)
    except (InputFileError, OutputFileError) as problem:
        return cli.unusable(problem)
    done = {tuple(row[column] for column in timing.KEY_COLUMNS) for row in existing}
    cli.say(
        f"{len(rows)} usable input rows, {len(problems)} skipped; {arguments.repeats} repeats; "
        f"{len(done)} rounds already in {results.path}"
    )
    parameters = {**cli.pacing_parameters(arguments), "repeats": arguments.repeats}
    run = new_run("measure_sources", HTTP if arguments.base_url else IN_PROCESS, parameters)
    stopped = cli.EXIT_OK
    if rows:
        try:
            _measure(arguments, rows, results, done, cli.pace_for(arguments, existing), run)
        except DailyAllowanceUsed as stop:
            cli.say(
                f"daily allowance used ({arguments.max_per_day} starts in 24 hours); "
                f"run the same command after {stop.again_at_text} to continue"
            )
            stopped = cli.EXIT_ALLOWANCE
        except KeyboardInterrupt:
            cli.say("interrupted; run the same command again to continue")
            stopped = cli.EXIT_INTERRUPTED
    wanted = {row.key for row in rows}
    shown = [
        row for row in results.rows()
        if tuple(row[column] for column in timing.KEY_COLUMNS[:3]) in wanted
    ]  # fmt: skip
    summaries = timing_stats.summarise(shown)
    cli.emit(
        arguments, run, shown, timing_stats.markdown(summaries),
        csv_text(timing_stats.SUMMARY_COLUMNS, summaries),
    )  # fmt: skip
    if stopped:
        return stopped
    if not rows:
        cli.say("error: the input file has no usable rows")
        return cli.EXIT_UNUSABLE
    failed = any(
        row["source"] == timing.ANALYSIS_TOTAL and row["ok"] != "true" for row in shown
    )
    return cli.EXIT_PROBLEMS if failed or problems else cli.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
