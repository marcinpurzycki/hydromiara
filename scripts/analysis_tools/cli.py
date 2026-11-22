"""What the two command line tools share: options, input, output file, final table."""

import argparse
import sys
from collections.abc import Mapping, Sequence

from analysis_tools import inputs, pacing
from analysis_tools.inputs import InputFileError, InputRow
from analysis_tools.pacing import Pace
from analysis_tools.service import RunInfo
from analysis_tools.tables import OutputFileError, ResultFile, parse_time, write_text
from app.catalog.crops import has_crop, list_crops
from app.orchestrator.runtime import local_today

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_UNUSABLE = 2
EXIT_ALLOWANCE = 3
EXIT_INTERRUPTED = 130


def say(message: str) -> None:
    """Progress goes to the error stream; the standard output carries only the table."""
    print(message, file=sys.stderr, flush=True)


def parser(description: str, default_output: str) -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    made.add_argument("input", help="CSV file with the analyses to run (format above)")
    made.add_argument(
        "--output", default=default_output,
        help="CSV file the rows are appended to; an existing file is continued "
        "(default: %(default)s)",
    )  # fmt: skip
    made.add_argument(
        "--base-url",
        help="address of a running service, e.g. https://example.org; analyses then go "
        "over HTTP instead of running in this process",
    )
    made.add_argument(
        "--spacing", type=float, default=pacing.DEFAULT_SPACING_S,
        help="shortest time in seconds between two starts (default: %(default)s; "
        "keeps the load on the free services low)",
    )  # fmt: skip
    made.add_argument(
        "--max-per-hour", type=int, default=pacing.DEFAULT_PER_HOUR,
        help="starts allowed within an hour, 0 for no cap (default: %(default)s; "
        "the free weather archive allows about 85 analyses per hour)",
    )  # fmt: skip
    made.add_argument(
        "--max-per-day", type=int, default=pacing.DEFAULT_PER_DAY,
        help="starts allowed within 24 hours, 0 for no cap (default: %(default)s; "
        "the free weather archive allows about 170 analyses per day)",
    )  # fmt: skip
    made.add_argument(
        "--concurrency", type=int, default=1,
        help="analyses running at the same time (default: %(default)s); starts stay spaced",
    )  # fmt: skip
    made.add_argument(
        "--format", choices=("markdown", "csv", "none"), default="markdown",
        help="what is printed at the end: a Markdown table to paste, the rows as CSV, "
        "or nothing (default: %(default)s)",
    )  # fmt: skip
    made.add_argument("--markdown", metavar="FILE", help="also write the Markdown table here")
    made.add_argument(
        "--raw", metavar="FILE", help="also append the raw results here, one JSON document per line"
    )
    made.add_argument(
        "--verbose", action="store_true", help="show the log of the service running in this process"
    )
    return made


def read_rows(arguments: argparse.Namespace) -> tuple[list[InputRow], list[inputs.InputProblem]]:
    """Usable rows of the input file; problems are printed with their line numbers.

    With a running service the crop is not checked here: its own catalogue
    decides, and an unknown crop comes back as the reason of a failed row.
    """
    local = not arguments.base_url
    rows, problems = inputs.read_input(
        arguments.input,
        today=local_today(),
        known_crop=has_crop if local else None,
        crop_ids=tuple(crop.id for crop in list_crops()) if local else (),
    )
    for problem in problems:
        say(f"{arguments.input}: {problem} (row skipped)")
    return rows, problems


def open_output(arguments: argparse.Namespace, columns: Sequence[str]):
    """The output file and the rows it already holds."""
    results = ResultFile(arguments.output, columns)
    return results, results.rows()


def pace_for(arguments: argparse.Namespace, earlier_rows: Sequence[Mapping[str, str]]) -> Pace:
    """The pace of this run; starts recorded in the output file count towards the caps."""
    moments = {row.get("started_at", "") for row in earlier_rows}
    earlier = [moment for moment in map(parse_time, moments) if moment is not None]
    return Pace(
        arguments.spacing, arguments.max_per_hour, arguments.max_per_day, earlier=earlier
    )


def pacing_parameters(arguments: argparse.Namespace) -> dict:
    return {
        "input": arguments.input,
        "spacing_s": arguments.spacing,
        "max_per_hour": arguments.max_per_hour,
        "max_per_day": arguments.max_per_day,
        "concurrency": arguments.concurrency,
        "base_url": arguments.base_url,
    }


def provenance(rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Where and when the shown rows were measured; they may come from several runs."""
    if not rows:
        return []

    def distinct(column: str) -> str:
        return ", ".join(sorted({row[column] for row in rows if row[column]})) or "unknown"

    starts = sorted(row["started_at"] for row in rows if row["started_at"])
    span = f"{starts[0]} to {starts[-1]} (UTC)" if starts else "unknown"
    return [
        f"Rows measured {span}; code {distinct('code_version')}; host {distinct('host')}; "
        f"mode {distinct('mode')}."
    ]


def emit(
    arguments: argparse.Namespace,
    run: RunInfo | None,
    rows: Sequence[Mapping[str, str]],
    table: str,
    as_csv: str,
) -> None:
    """Print the final table in the chosen format and write the Markdown file."""
    heading = [*(run.lines() if run else []), *provenance(rows)]
    document = "\n".join(heading) + "\n\n" + table
    if arguments.markdown:
        write_text(arguments.markdown, document)
        say(f"Markdown table written to {arguments.markdown}")
    if arguments.format == "markdown":
        print(document, end="")
    elif arguments.format == "csv":
        print(as_csv, end="")


def unusable(problem: InputFileError | OutputFileError) -> int:
    say(f"error: {problem}")
    return EXIT_UNUSABLE
