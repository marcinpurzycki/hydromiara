"""Output of the tools: a CSV file written row by row, and Markdown tables.

The CSV file is the record of a run. Rows are appended and flushed as soon as
they exist, so an interrupted run loses nothing, and the next run with the same
output file continues where the previous one stopped: rows already in the file
are not run again. Column names are fixed; every value is text.
"""

import csv
import io
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path


class OutputFileError(Exception):
    """The output file exists but was not written with these columns."""


def text(value: object) -> str:
    """One spelling per kind of value: empty for none, true/false, at most 3 decimals."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def joined(values: Iterable[object]) -> str:
    """Several values in one cell."""
    return ";".join(text(value) for value in values)


def parse_time(value: str) -> datetime | None:
    """A time written by `service.timestamp`; None for anything else."""
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


class ResultFile:
    """A CSV file with fixed columns that grows by appended rows."""

    def __init__(self, path: str | Path, columns: Sequence[str]) -> None:
        self.path = Path(path)
        self.columns = tuple(columns)

    def rows(self) -> list[dict[str, str]]:
        """Rows written so far; empty when the file does not exist yet."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        with self.path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != self.columns:
                raise OutputFileError(
                    f"{self.path} has other columns than this version of the tool writes; "
                    "choose another output file or move the old one away"
                )
            return [dict(row) for row in reader]

    def append(self, rows: Iterable[Mapping[str, object]]) -> None:
        """Add rows at the end and make sure they are on disk."""
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.columns)
            if new_file:
                writer.writeheader()
            for row in rows:
                writer.writerow({column: text(row.get(column)) for column in self.columns})
            handle.flush()
            os.fsync(handle.fileno())

    def rewrite(self, rows: Iterable[Mapping[str, object]]) -> None:
        """Replace the content: used to drop rows that will be run again."""
        kept = list(rows)
        temporary = self.path.with_name(self.path.name + ".tmp")
        ResultFile(temporary, self.columns).append(kept)
        os.replace(temporary, self.path)


def append_json_line(path: str | Path, record: Mapping[str, object]) -> None:
    """One JSON document per line: the raw results, written as they come."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def csv_text(columns: Sequence[str], rows: Iterable[Mapping[str, object]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: text(row.get(column)) for column in columns})
    return buffer.getvalue()


def _cell(value: object) -> str:
    return text(value).replace("|", "\\|").replace("\n", " ").strip()


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    """A pipe table ready to paste into a Markdown document."""
    lines = [
        "| " + " | ".join(_cell(header) for header in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return "\n".join(lines) + "\n"


def write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
