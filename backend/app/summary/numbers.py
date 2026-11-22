"""Reading numbers, dates and units out of a text, so that two texts can be compared.

Notation is normalised, so that the same value written differently compares
equal: decimal comma and point ("1,15" = "1.15" = "1,150"), digit groups
("1 360" = "1360"), dates as "20.06.2023", "2023-06-20" or "20 czerwca 2023",
day and month as "15.05", per cent as "%" or "procent". Signs are not read and
numbers written in words are not recognised.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.summary import params

_DATE_FULL = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DAY_MONTH = re.compile(r"(?<![\d.,])(\d{1,2})\.(\d{2})(?!\d)")
_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?")
_GROUPED = re.compile(r"(?<![\w.,])\d{1,3}(?: \d{3})+(?![\d.,])")
_YEAR_PAIR = re.compile(r"(?<!\d)(\d+) z (\d+)\s+(?:\w+\s+)?lat", re.IGNORECASE)
_UNIT = re.compile(
    r"\s*(?:" + "|".join(f"(?P<{name}>{pattern})" for name, pattern in params.UNIT_PATTERNS) + ")",
    re.IGNORECASE,
)
_RANGE_LINK = re.compile(r"\s*(?:do|–|—|-|i|lub|albo)\s*", re.IGNORECASE)
_MONTHS = [re.compile(pattern, re.IGNORECASE) for pattern in params.MONTH_PATTERNS]


@dataclass(frozen=True)
class Token:
    value: Decimal
    unit: str | None
    start: int
    end: int


@dataclass
class Numbers:
    tokens: list[Token] = field(default_factory=list)
    # Digit groups read as one number; their parts are also among the tokens.
    groups: list[Token] = field(default_factory=list)
    dates: set[tuple[int, int, int]] = field(default_factory=set)
    day_months: set[tuple[int, int]] = field(default_factory=set)
    # "15.05": a day and month or a decimal number; both readings are kept.
    ambiguous: list[tuple[int, int, Decimal]] = field(default_factory=list)
    months: set[int] = field(default_factory=set)
    year_pairs: set[tuple[int, int]] = field(default_factory=set)

    def values(self) -> set[Decimal]:
        """Values written as numbers, including the decimal reading of "15.05"."""
        values = {token.value for token in (*self.tokens, *self.groups)}
        return values | {decimal for _day, _month, decimal in self.ambiguous}

    def date_parts(self) -> dict[Decimal, set[str | None]]:
        """Day, month and year numbers of the dates, with the units they may carry.

        They let "20.06.2023" be written as "20 czerwca 2023 r."; such a number
        is not accepted with a unit of measure.
        """
        parts: dict[Decimal, set[str | None]] = {}
        for day, month, year in self.dates:
            parts.setdefault(Decimal(day), set()).add(None)
            parts.setdefault(Decimal(month), set()).add(None)
            parts.setdefault(Decimal(year), set()).update((None, "years"))
        for day, month, _decimal in self.ambiguous:
            parts.setdefault(Decimal(day), set()).add(None)
            parts.setdefault(Decimal(month), set()).add(None)
        return parts

    def units(self) -> dict[Decimal, set[str | None]]:
        """Units each value appears with; None stands for "without a unit"."""
        units: dict[Decimal, set[str | None]] = {}
        for token in (*self.tokens, *self.groups):
            units.setdefault(token.value, set()).add(token.unit)
        return units


def _decimal(text: str) -> Decimal:
    return Decimal(text.replace(" ", "").replace(",", "."))


def _unit_after(text: str, end: int) -> str | None:
    match = _UNIT.match(text, end)
    return None if match is None else match.lastgroup


def _valid_day_month(day: int, month: int) -> bool:
    return 1 <= day <= 31 and 1 <= month <= 12


def _with_range_units(text: str, tokens: list[Token]) -> list[Token]:
    """In "od 54 do 136 mm" the unit belongs to both numbers."""
    result = list(tokens)
    for index in range(len(result) - 2, -1, -1):
        token, following = result[index], result[index + 1]
        if token.unit is None and following.unit is not None:
            if _RANGE_LINK.fullmatch(text, token.end, following.start):
                result[index] = Token(token.value, following.unit, token.start, token.end)
    return result


def read_numbers(text: str) -> Numbers:
    text = text.replace(" ", " ").replace(" ", " ")
    found = Numbers()
    found.months = {index + 1 for index, month in enumerate(_MONTHS) if month.search(text)}
    found.year_pairs = {(int(a), int(b)) for a, b in _YEAR_PAIR.findall(text)}

    def blank(match: re.Match[str]) -> str:
        return " " * len(match.group(0))

    def full_date(match: re.Match[str]) -> str:
        day, month, year = (int(part) for part in match.groups())
        if not _valid_day_month(day, month):
            return match.group(0)
        found.dates.add((day, month, year))
        return blank(match)

    def iso_date(match: re.Match[str]) -> str:
        year, month, day = (int(part) for part in match.groups())
        if not _valid_day_month(day, month):
            return match.group(0)
        found.dates.add((day, month, year))
        return blank(match)

    def day_month(match: re.Match[str]) -> str:
        day, month = int(match.group(1)), int(match.group(2))
        if not _valid_day_month(day, month):
            return match.group(0)
        found.ambiguous.append((day, month, _decimal(match.group(0))))
        return blank(match)

    text = _DATE_FULL.sub(full_date, text)
    text = _DATE_ISO.sub(iso_date, text)
    text = _DAY_MONTH.sub(day_month, text)
    for day, month, _year in found.dates:
        found.day_months.add((day, month))
        found.months.add(month)
    for day, month, _decimal_value in found.ambiguous:
        found.day_months.add((day, month))
        found.months.add(month)
    found.groups = [
        Token(_decimal(m.group(0)), _unit_after(text, m.end()), m.start(), m.end())
        for m in _GROUPED.finditer(text)
    ]
    tokens = [
        Token(_decimal(m.group(0)), _unit_after(text, m.end()), m.start(), m.end())
        for m in _NUMBER.finditer(text)
    ]
    found.tokens = _with_range_units(text, tokens)
    return found


def numbers_problem(answer: Numbers, source: Numbers) -> str | None:
    """Why the numbers of the answer do not follow from the source; None when they do."""
    if not answer.dates <= source.dates:
        return "date_not_in_report"
    if not answer.months <= source.months:
        return "month_not_in_report"
    if not answer.year_pairs <= source.year_pairs:
        return "year_count_not_in_report"
    values, units, date_parts = source.values(), source.units(), source.date_parts()
    for day, month, decimal in answer.ambiguous:
        if (day, month) not in source.day_months and decimal not in values:
            return "number_not_in_report"
    accepted = [group for group in answer.groups if group.value in values]
    for token in answer.tokens:
        if any(group.start <= token.start and token.end <= group.end for group in accepted):
            continue
        if token.value in values:
            accepted.append(token)
        elif token.unit not in date_parts.get(token.value, ()):
            return "number_not_in_report"
    for token in accepted:
        known = units.get(token.value)
        # A value the source has only with other units must not change its unit.
        if token.unit and known and None not in known and token.unit not in known:
            return "unit_changed"
    return None
