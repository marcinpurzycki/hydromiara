"""Checks of what a client sends in a path or in the request, shared by the routes.

Every value is checked before it reaches the database or an external
service: its length, its characters and, for a date, its range.
"""

import re
from datetime import date
from typing import Annotated

from fastapi import Depends

from app.api import limits
from app.api.errors import ApiError
from app.sources.parcel_query import is_parcel_id

# Report identifiers are URL-safe random text; the example report is "demo".
_REPORT_ID = re.compile(rf"[A-Za-z0-9_-]{{1,{limits.MAX_REPORT_ID_CHARS}}}")
# After the three fixed parts of a parcel identifier: sheet and parcel number.
_PARCEL_ID_CHARS = re.compile(r"[\w./-]+")


def _known_report_id(report_id: str) -> str:
    """A text that cannot be a report identifier is answered like an unknown Report."""
    if _REPORT_ID.fullmatch(report_id) is None:
        raise ApiError(404, "report_not_found", "Nie ma takiego raportu.")
    return report_id


# Path parameter `report_id` of every route that takes one.
ReportId = Annotated[str, Depends(_known_report_id)]


def is_plain_text(text: str) -> bool:
    """No control characters and nothing else that cannot be shown."""
    return text.isprintable()


def has_parcel_id_form(parcel_id: str) -> bool:
    """True for a text of the length, form and characters of a full parcel identifier."""
    text = parcel_id.strip()
    return (
        len(text) <= limits.MAX_PARCEL_ID_CHARS
        and is_parcel_id(text)
        and _PARCEL_ID_CHARS.fullmatch(text) is not None
    )


def require_parcel_id(parcel_id: str) -> str:
    """Raise unless the text has the form of a full parcel identifier; returns it trimmed."""
    text = parcel_id.strip()
    if not has_parcel_id_form(text):
        raise ApiError(
            422,
            "invalid_parcel_id",
            "Podaj pełny identyfikator działki, np. 040704_2.0020.34/2.",
        )
    return text


def require_analysis_date(analysis_date: date, today: date) -> None:
    """Raise unless the analysis date lies between the earliest accepted date and today."""
    if analysis_date > today:
        raise ApiError(
            422, "analysis_date_in_future", "Data analizy nie może być późniejsza niż dzisiejsza."
        )
    if analysis_date < limits.EARLIEST_ANALYSIS_DATE:
        raise ApiError(
            422,
            "analysis_date_too_early",
            "Data analizy nie może być wcześniejsza niż "
            f"{limits.EARLIEST_ANALYSIS_DATE:%d.%m.%Y}.",
        )
