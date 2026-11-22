"""The input list of the tools: one analysis per row of a CSV file.

Format (UTF-8, comma or semicolon separated, first row is the header):

    parcel_id,crop_id,analysis_date,label,region
    040704_2.0020.34/2,winter_wheat,2023-06-20,Kujawy dry year,kujawsko-pomorskie

Required columns: `parcel_id` (full cadastral identifier), `crop_id`
(identifier from the crop catalogue), `analysis_date` (YYYY-MM-DD, or the word
`today`). Optional columns: `label` and `region`, free text copied to the
output. Other columns are ignored. Empty lines and lines starting with `#`
are skipped. The file must not hold personal data: only parcel identifiers,
crops and dates are sent to the data sources.

A row that cannot be used is reported with its line number and left out; the
remaining rows are still run.
"""

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.sources.parcel_query import is_parcel_id

REQUIRED_COLUMNS = ("parcel_id", "crop_id", "analysis_date")
OPTIONAL_COLUMNS = ("label", "region")
TODAY_WORD = "today"
# The analysis request accepts identifiers up to this length.
MAX_FIELD_CHARS = 64
MAX_NOTE_CHARS = 120


class InputFileError(Exception):
    """The whole file cannot be used (missing, empty, without the required columns)."""


@dataclass(frozen=True)
class InputRow:
    line: int
    parcel_id: str
    crop_id: str
    analysis_date: date
    label: str = ""
    region: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        """What identifies an analysis: the same key always means the same request."""
        return (self.parcel_id, self.crop_id, self.analysis_date.isoformat())

    @property
    def name(self) -> str:
        return f"{self.parcel_id} {self.crop_id} {self.analysis_date.isoformat()}"


@dataclass(frozen=True)
class InputProblem:
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


def _content_lines(text: str) -> list[tuple[int, str]]:
    """Lines that carry data, with their numbers in the file (from 1)."""
    return [
        (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _split(line: str, delimiter: str) -> list[str]:
    return [cell.strip() for cell in next(csv.reader([line], delimiter=delimiter))]


def _parse_date(text: str, today: date) -> date:
    if text.lower() == TODAY_WORD:
        return today
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"analysis_date '{text}' is not a date in the form YYYY-MM-DD (or '{TODAY_WORD}')"
        ) from None


def _parse_row(
    line: int,
    cells: dict[str, str],
    today: date,
    known_crop: Callable[[str], bool] | None,
    crop_hint: str,
) -> InputRow:
    for column in REQUIRED_COLUMNS:
        if not cells.get(column):
            raise ValueError(f"{column} is empty")
    parcel_id, crop_id = cells["parcel_id"], cells["crop_id"]
    if len(parcel_id) > MAX_FIELD_CHARS or not is_parcel_id(parcel_id):
        raise ValueError(
            f"parcel_id '{parcel_id}' is not a full parcel identifier "
            "(expected the form 040704_2.0020.34/2)"
        )
    if len(crop_id) > MAX_FIELD_CHARS or (known_crop is not None and not known_crop(crop_id)):
        raise ValueError(f"crop_id '{crop_id}' is not in the crop catalogue{crop_hint}")
    analysis_date = _parse_date(cells["analysis_date"], today)
    if analysis_date > today:
        raise ValueError(f"analysis_date {analysis_date.isoformat()} is in the future")
    return InputRow(
        line=line,
        parcel_id=parcel_id,
        crop_id=crop_id,
        analysis_date=analysis_date,
        label=cells.get("label", "")[:MAX_NOTE_CHARS],
        region=cells.get("region", "")[:MAX_NOTE_CHARS],
    )


def parse_input(
    text: str,
    *,
    today: date,
    known_crop: Callable[[str], bool] | None = None,
    crop_ids: tuple[str, ...] = (),
) -> tuple[list[InputRow], list[InputProblem]]:
    """Usable rows and the problems of the others.

    `known_crop` tells whether a crop identifier can be analysed; None skips
    the check (the service that runs the analysis decides). `crop_ids` are
    named in the message about an unknown crop.
    """
    lines = _content_lines(text)
    if not lines:
        raise InputFileError("the input file has no header row")
    header_line, header_text = lines[0]
    delimiter = ";" if ";" in header_text and "," not in header_text else ","
    header = [name.lower() for name in _split(header_text, delimiter)]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise InputFileError(
            f"line {header_line}: the header lacks the column(s) {', '.join(missing)}; "
            f"required: {', '.join(REQUIRED_COLUMNS)}; optional: {', '.join(OPTIONAL_COLUMNS)}"
        )
    crop_hint = f" (available: {', '.join(crop_ids)})" if crop_ids else ""
    rows: list[InputRow] = []
    problems: list[InputProblem] = []
    first_line_of: dict[tuple[str, str, str], int] = {}
    for line, content in lines[1:]:
        values = _split(content, delimiter)
        if len(values) > len(header):
            problems.append(
                InputProblem(line, f"{len(values)} values for {len(header)} header columns")
            )
            continue
        cells = dict(zip(header, values))
        try:
            row = _parse_row(line, cells, today, known_crop, crop_hint)
        except ValueError as problem:
            problems.append(InputProblem(line, str(problem)))
            continue
        if row.key in first_line_of:
            problems.append(
                InputProblem(line, f"repeats the analysis of line {first_line_of[row.key]}")
            )
            continue
        first_line_of[row.key] = line
        rows.append(row)
    return rows, problems


def read_input(
    path: str | Path,
    *,
    today: date,
    known_crop: Callable[[str], bool] | None = None,
    crop_ids: tuple[str, ...] = (),
) -> tuple[list[InputRow], list[InputProblem]]:
    try:
        # utf-8-sig: spreadsheet exports often start with a byte order mark.
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as problem:
        raise InputFileError(f"cannot read the input file {path}: {problem.strerror}") from None
    except UnicodeDecodeError:
        raise InputFileError(f"the input file {path} is not UTF-8 text") from None
    return parse_input(text, today=today, known_crop=known_crop, crop_ids=crop_ids)
