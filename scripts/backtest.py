#!/usr/bin/env python3
"""Backtest: run ordinary analyses for a list of parcels and dates, write a table.

Every row of the input file is analysed with the application's own code and
the live data sources, exactly like a request from the web application, and
gives one row of the output: both verdicts with their confidence, the class of
the independent drought indicator and the result of the consistency check, the
causes found, which sources answered and how long everything took. A failed
analysis gives a row with the reason. Choosing the parcels and reading the
results is not this tool's job.

Input: a CSV file with the header `parcel_id,crop_id,analysis_date` and
optionally `label,region`; dates as YYYY-MM-DD or `today`; lines starting with
`#` are comments. Example of the format: scripts/examples/input_format_example.csv.

Output: the CSV file given by --output (default backtest-results.csv), one row
per analysis, written after every analysis. Running the same command again
continues an interrupted run: analyses already in the output file are skipped
(--retry-failed runs the failed ones again). At the end a short Markdown
table is printed. Result files are not meant to be committed.

Run from the repository root with the backend's Python environment:

    EDO_DATA_PATH=/path/to/drought/files backend/.venv/bin/python scripts/backtest.py \\
        scripts/examples/input_format_example.csv

Against a running service (end to end, source times not available):

    backend/.venv/bin/python scripts/backtest.py INPUT.csv --base-url https://example.org

Inside the service image (no change of the image; results land in ./results):

    docker compose run --rm --no-deps -u "$(id -u)" -e PROBE_HOST="$(hostname)" \\
        -e CODE_VERSION="$(git rev-parse --short HEAD)" \\
        -v "$PWD/scripts:/srv/scripts:ro" -v "$PWD/results:/results" api \\
        python scripts/backtest.py scripts/examples/input_format_example.csv \\
        --output /results/backtest-results.csv

Pace: analyses run one after another, 13 s apart, at most 50 per hour and 100
per day, which keeps the free data services within their limits (see
scripts/analysis_tools/pacing.py). Exit status: 0 all analyses done, 1 some
failed or some input rows were skipped, 2 input or output file unusable,
3 stopped at the daily cap (run again later to continue).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis_tools import cli  # noqa: E402
from analysis_tools.backtest_rows import COLUMNS, markdown, result_row  # noqa: E402
from analysis_tools.inputs import InputFileError, InputRow  # noqa: E402
from analysis_tools.pacing import DailyAllowanceUsed  # noqa: E402
from analysis_tools.runner import DONE, AnalysisResult, run_analyses  # noqa: E402
from analysis_tools.service import HTTP, IN_PROCESS, RunInfo, new_run, open_service  # noqa: E402
from analysis_tools.tables import OutputFileError, append_json_line, csv_text  # noqa: E402

DEFAULT_OUTPUT = "backtest-results.csv"


def _key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row["parcel_id"], row["crop_id"], row["analysis_date"])


def _progress(result: AnalysisResult, row: dict) -> str:
    took = "" if result.total_s is None else f" in {result.total_s:.1f} s"
    if not result.done:
        return f"  failed{took}: {result.failure}"
    years = f"{row['multiyear_deficit_years']}/{row['multiyear_total_years']}"
    return (
        f"  done{took}: {row['current_label']}; deficit years {years}; "
        f"consistency {row['consistency_result']}; without data: {row['sources_missing'] or '-'}"
    )


def _raw(result: AnalysisResult, row: dict, run: RunInfo) -> dict:
    return {
        "run": run.as_dict(),
        "row": row,
        "status": result.status,
        "report": result.report_json,
        "source_outcomes": [outcome.model_dump(mode="json") for outcome in result.outcomes],
    }


def _run(arguments, pending: list[InputRow], results, earlier: list[dict], run: RunInfo) -> int:
    """Analyse the pending rows; returns the exit status of an early stop, else 0."""
    pace = cli.pace_for(arguments, earlier)
    try:
        with open_service(arguments.base_url, quiet=not arguments.verbose) as service:
            for result in run_analyses(
                service, pending, pace, concurrency=arguments.concurrency, announce=cli.say
            ):
                row = result_row(result, run)
                results.append([row])
                if arguments.raw:
                    append_json_line(arguments.raw, _raw(result, row, run))
                cli.say(_progress(result, row))
    except DailyAllowanceUsed as stop:
        cli.say(
            f"daily allowance used ({arguments.max_per_day} starts in 24 hours); "
            f"run the same command after {stop.again_at_text} to continue"
        )
        return cli.EXIT_ALLOWANCE
    except KeyboardInterrupt:
        cli.say("interrupted; run the same command again to continue")
        return cli.EXIT_INTERRUPTED
    return cli.EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = cli.parser(__doc__, DEFAULT_OUTPUT)
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="run again the analyses that are in the output file as failed",
    )  # fmt: skip
    arguments = parser.parse_args(argv)
    try:
        rows, problems = cli.read_rows(arguments)
        results, existing = cli.open_output(arguments, COLUMNS)
    except (InputFileError, OutputFileError) as problem:
        return cli.unusable(problem)
    if arguments.retry_failed and any(row["status"] != DONE for row in existing):
        existing = [row for row in existing if row["status"] == DONE]
        results.rewrite(existing)
    known = {_key(row) for row in existing}
    pending = [row for row in rows if row.key not in known]
    cli.say(
        f"{len(rows)} usable input rows, {len(problems)} skipped; "
        f"{len(rows) - len(pending)} already in {results.path}, {len(pending)} to run"
    )
    run = new_run(
        "backtest", HTTP if arguments.base_url else IN_PROCESS, cli.pacing_parameters(arguments)
    )
    stopped = _run(arguments, pending, results, existing, run) if pending else cli.EXIT_OK
    wanted = {row.key: position for position, row in enumerate(rows)}
    shown = sorted(
        (row for row in results.rows() if _key(row) in wanted), key=lambda row: wanted[_key(row)]
    )
    cli.emit(arguments, run, shown, markdown(shown), csv_text(COLUMNS, shown))
    if stopped:
        return stopped
    if not rows:
        cli.say("error: the input file has no usable rows")
        return cli.EXIT_UNUSABLE
    complete = len(shown) == len(rows) and all(row["status"] == DONE for row in shown)
    return cli.EXIT_OK if complete and not problems else cli.EXIT_PROBLEMS


if __name__ == "__main__":
    sys.exit(main())
