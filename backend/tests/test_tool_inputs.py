"""The input list of the command line tools: rows, problems with line numbers."""

from datetime import date

import pytest

from app.catalog.crops import has_crop
from tests.tool_helpers import EXAMPLE_INPUT, HEADER, KNOWN_ID

from analysis_tools.inputs import InputFileError, parse_input, read_input  # isort: skip

TODAY = date(2026, 11, 21)


def parse(text: str, **options):
    return parse_input(text, today=TODAY, known_crop=has_crop, **options)


def messages(problems) -> list[str]:
    return [str(problem) for problem in problems]


def test_valid_rows_keep_their_values_and_line_numbers():
    rows, problems = parse(
        "# a comment\n\n" + HEADER + f"{KNOWN_ID},winter_wheat,2023-06-20,dry year,Kujawy\n"
        "141201_1.0001.6509,bare_field,2019-06-15,,\n"
    )
    assert problems == []
    assert [(row.line, row.parcel_id, row.crop_id) for row in rows] == [
        (4, KNOWN_ID, "winter_wheat"),
        (5, "141201_1.0001.6509", "bare_field"),
    ]
    assert rows[0].analysis_date == date(2023, 6, 20)
    assert (rows[0].label, rows[0].region) == ("dry year", "Kujawy")
    assert rows[0].key == (KNOWN_ID, "winter_wheat", "2023-06-20")
    assert (rows[1].label, rows[1].region) == ("", "")


def test_optional_columns_may_be_absent_and_unknown_columns_are_ignored():
    rows, problems = parse(
        "analysis_date,note,crop_id,parcel_id\n2023-06-20,anything,winter_wheat," + KNOWN_ID + "\n"
    )
    assert problems == []
    assert rows[0].key == (KNOWN_ID, "winter_wheat", "2023-06-20")
    assert rows[0].label == ""


def test_semicolon_separated_file_and_the_word_today():
    rows, problems = parse(
        "parcel_id;crop_id;analysis_date\n" + KNOWN_ID + ";winter_wheat;today\n"
    )
    assert problems == []
    assert rows[0].analysis_date == TODAY


@pytest.mark.parametrize("text", ["", "\n\n", "# only a comment\n"])
def test_file_without_a_header_is_unusable(text):
    with pytest.raises(InputFileError, match="no header"):
        parse(text)


def test_header_alone_gives_no_rows_and_no_problems():
    assert parse(HEADER) == ([], [])


def test_missing_columns_are_named():
    with pytest.raises(InputFileError) as raised:
        parse("parcel_id,date\n" + KNOWN_ID + ",2023-06-20\n")
    assert "line 1" in str(raised.value)
    assert "crop_id, analysis_date" in str(raised.value)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (f"{KNOWN_ID},winter_wheat,20.06.2023,,", "analysis_date '20.06.2023' is not a date"),
        (f"{KNOWN_ID},winter_wheat,2023-02-30,,", "analysis_date '2023-02-30' is not a date"),
        (f"{KNOWN_ID},winter_wheat,2026-11-22,,", "analysis_date 2026-11-22 is in the future"),
        (f"{KNOWN_ID},sunflower,2023-06-20,,", "crop_id 'sunflower' is not in the crop catalogue"),
        ("Brzoza 125/3,winter_wheat,2023-06-20,,", "is not a full parcel identifier"),
        ("125/3,winter_wheat,2023-06-20,,", "is not a full parcel identifier"),
        (f"{KNOWN_ID},,2023-06-20,,", "crop_id is empty"),
        (f",winter_wheat,2023-06-20,,", "parcel_id is empty"),
        (f"{KNOWN_ID},winter_wheat,2023-06-20,a,b,c", "6 values for 5 header columns"),
    ],
)
def test_bad_row_is_reported_with_its_line_and_does_not_stop_the_rest(line, expected):
    rows, problems = parse(HEADER + line + "\n" + f"{KNOWN_ID},winter_wheat,2019-06-15,,\n")
    assert [row.line for row in rows] == [3]
    assert len(problems) == 1
    assert problems[0].line == 2
    assert expected in problems[0].message
    assert str(problems[0]).startswith("line 2: ")


def test_unknown_crop_message_names_the_available_crops():
    _, problems = parse(
        HEADER + f"{KNOWN_ID},sunflower,2023-06-20,,\n", crop_ids=("winter_wheat", "bare_field")
    )
    assert "(available: winter_wheat, bare_field)" in problems[0].message


def test_crop_is_not_checked_when_the_service_decides():
    rows, problems = parse_input(
        HEADER + f"{KNOWN_ID},maize,2023-06-20,,\n", today=TODAY, known_crop=None
    )
    assert problems == []
    assert rows[0].crop_id == "maize"


def test_any_catalogue_crop_is_accepted():
    accepted = {"winter_wheat", "spring_barley"}
    rows, problems = parse_input(
        HEADER + f"{KNOWN_ID},spring_barley,2023-06-20,,\n",
        today=TODAY,
        known_crop=accepted.__contains__,
    )
    assert problems == []
    assert rows[0].crop_id == "spring_barley"


def test_repeated_analysis_is_reported_with_the_first_line():
    row = f"{KNOWN_ID},winter_wheat,2023-06-20,,\n"
    rows, problems = parse(HEADER + row + f"{KNOWN_ID},winter_wheat,2019-06-15,,\n" + row)
    assert [r.line for r in rows] == [2, 3]
    assert messages(problems) == ["line 4: repeats the analysis of line 2"]


def test_reading_a_file_with_a_byte_order_mark(tmp_path):
    path = tmp_path / "input.csv"
    path.write_bytes(b"\xef\xbb\xbf" + (HEADER + f"{KNOWN_ID},winter_wheat,2023-06-20,,\n").encode())
    rows, problems = read_input(path, today=TODAY, known_crop=has_crop)
    assert problems == []
    assert rows[0].parcel_id == KNOWN_ID


def test_missing_file_is_unusable(tmp_path):
    with pytest.raises(InputFileError, match="cannot read the input file"):
        read_input(tmp_path / "absent.csv", today=TODAY)


def test_example_file_is_valid_and_uses_catalogue_crops():
    rows, problems = read_input(EXAMPLE_INPUT, today=TODAY, known_crop=has_crop)
    assert problems == []
    assert len(rows) == 6
    assert len({row.parcel_id for row in rows}) == 3
    assert {row.crop_id for row in rows} == {"winter_wheat"}
