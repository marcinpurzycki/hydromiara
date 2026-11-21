"""Recognising what the user typed into the parcel search box.

Two forms are accepted: the full parcel identifier, or the parcel number
together with the name of the cadastral region, in either order.
"""

import re

# WWPPGG_R.OOOO.[AR_NR.]NR_DZ, e.g. 141201_1.0001.6509 or 060606_2.0014.AR_3.756
_PARCEL_ID = re.compile(r"^\d{6}_\d\.\d{4}\.\S+$")
# Parcel number within a region, e.g. 125/3 or 756.
_PARCEL_NUMBER = re.compile(r"^\d[\w./-]*$")

# Rough bounding box of Poland (extreme points 14°07'–24°09' E, 49°00'–54°50' N).
_POLAND_LON = (14.0, 24.2)
_POLAND_LAT = (49.0, 54.9)


class ParcelQueryError(ValueError):
    """The text is neither an identifier nor a number with a region name."""


def is_parcel_id(text: str) -> bool:
    return _PARCEL_ID.fullmatch(text.strip()) is not None


def _is_number(text: str) -> bool:
    return _PARCEL_NUMBER.fullmatch(text) is not None


def _region_and_number(text: str) -> tuple[str, str]:
    if "," in text:
        parts = [" ".join(part.split()) for part in text.split(",")]
        if len(parts) != 2 or not all(parts):
            raise ParcelQueryError(text)
        first, second = parts
        if _is_number(second) and not _is_number(first):
            return first, second
        if _is_number(first) and not _is_number(second):
            return second, first
        raise ParcelQueryError(text)

    tokens = text.split()
    if len(tokens) < 2:
        raise ParcelQueryError(text)
    if _is_number(tokens[-1]):
        return " ".join(tokens[:-1]), tokens[-1]
    if _is_number(tokens[0]):
        return " ".join(tokens[1:]), tokens[0]
    raise ParcelQueryError(text)


def normalize_query(text: str) -> str:
    """Turn user input into the `id` value the parcel service understands.

    The identifier is passed through; "125/3, Brzoza" and "Brzoza 125/3"
    both become "Brzoza 125/3", the only order the service accepts.
    """
    text = text.strip()
    if is_parcel_id(text):
        return text
    region, number = _region_and_number(text)
    return f"{region} {number}"


def in_poland(lon: float, lat: float) -> bool:
    """Cheap pre-check; points inside the box but abroad simply match no parcel."""
    return _POLAND_LON[0] <= lon <= _POLAND_LON[1] and _POLAND_LAT[0] <= lat <= _POLAND_LAT[1]
