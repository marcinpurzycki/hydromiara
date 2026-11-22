"""Closed crop list: lookup, crop coefficient curve, season and critical period.

Pure functions over the catalogue data: no network, no clock; the only state
is a memo of crop coefficient curves, which changes no result. The caller
always passes the day it asks about.
"""

from datetime import date
from typing import NamedTuple

from app.catalog.crop_data import BARE_SOIL_KC, CROPS
from app.catalog.crop_model import CatalogCrop, CropGrowth
from app.catalog.periods import (
    DateRange,
    last_occurrence,
    occurrence_containing,
    occurrence_starting_in,
    on_or_after,
)
from app.contracts.catalog import Crop

_BY_ID: dict[str, CatalogCrop] = {crop.id: crop for crop in CROPS}


class UnknownCropError(KeyError):
    """The identifier is not on the closed crop list."""


def list_crops() -> tuple[CatalogCrop, ...]:
    """All crops in the order shown to the user."""
    return CROPS


def get_crop(crop_id: str) -> CatalogCrop:
    try:
        return _BY_ID[crop_id]
    except KeyError:
        raise UnknownCropError(crop_id) from None


def has_crop(crop_id: str) -> bool:
    return crop_id in _BY_ID


def season_on(crop: CatalogCrop, day: date) -> DateRange | None:
    """The season that includes `day`; None outside the season and for the bare field."""
    return None if crop.season is None else occurrence_containing(crop.season, day)


def in_season(crop: CatalogCrop, day: date) -> bool:
    return season_on(crop, day) is not None


def last_season(crop: CatalogCrop, day: date) -> DateRange | None:
    """The latest season sown on or before `day` (running or finished); None for the bare field."""
    return None if crop.season is None else last_occurrence(crop.season, day)


def critical_period_on(crop: CatalogCrop, day: date) -> DateRange | None:
    """The critical period that includes `day`, or None."""
    if crop.critical_period is None:
        return None
    return occurrence_containing(crop.critical_period, day)


def last_critical_period(crop: CatalogCrop, day: date) -> DateRange | None:
    """The latest critical period that began on or before `day`; None for the bare field."""
    if crop.critical_period is None:
        return None
    return last_occurrence(crop.critical_period, day)


class _SeasonCurve(NamedTuple):
    """Crop coefficient curve of one season: dated nodes joined by straight lines."""

    growth: CropGrowth
    start: date
    end: date
    nodes: tuple[tuple[date, float], ...]


# Curves already built, by (identity of the crop parameters, year of sowing,
# bare-soil coefficient). A curve is a pure function of its key, so keeping it
# changes no result; an entry holds its parameters, so their identity stays
# unique for as long as the entry exists. A year of daily balance asks for the
# same curve hundreds of times.
_CURVES: dict[tuple[int, int, float], _SeasonCurve] = {}
_MAX_CURVES = 4096


def _season_curve(growth: CropGrowth, year: int, bare: float) -> _SeasonCurve:
    """The curve of the season sown in the given calendar year."""
    key = (id(growth), year, bare)
    found = _CURVES.get(key)
    if found is not None and found.growth is growth:
        return found
    season = occurrence_starting_in(growth.season.value, year)
    stages = growth.stages.value
    ini, mid, end = growth.kc_ini.value, growth.kc_mid.value, growth.kc_end.value
    nodes: list[tuple[date, float]] = [
        (season.start, bare),
        (on_or_after(stages.establishment_end, season.start), ini),
        (on_or_after(stages.development_start, season.start), ini),
        (on_or_after(stages.mid_start, season.start), mid),
        (on_or_after(stages.late_start, season.start), mid),
    ]
    if stages.maturity is not None:
        nodes.append((on_or_after(stages.maturity, season.start), end))
    nodes.append((season.end, end))
    curve = _SeasonCurve(growth, season.start, season.end, tuple(nodes))
    if len(_CURVES) >= _MAX_CURVES:
        _CURVES.clear()
    _CURVES[key] = curve
    return curve


def kc(crop: CatalogCrop, day: date, *, bare_soil_kc: float | None = None) -> float:
    """Crop coefficient Kc of the crop on the given day.

    Inside the season the value follows the stage curve of the crop (flat
    stages joined by linear changes, counted in real days, so leap years are
    handled). The fall of the late stage ends on the maturity date when the
    crop has one, otherwise at harvest. Outside the season, and for the field
    without a crop, it is the bare-soil coefficient; `bare_soil_kc` overrides
    the catalogue value.
    """
    bare = BARE_SOIL_KC.value if bare_soil_kc is None else bare_soil_kc
    growth = crop.growth
    if growth is None:
        return bare
    for year in (day.year - 1, day.year):
        curve = _season_curve(growth, year, bare)
        if curve.start <= day <= curve.end:
            break
    else:
        return bare
    nodes = curve.nodes
    for (left, left_kc), (right, right_kc) in zip(nodes, nodes[1:]):
        if left < right and left <= day <= right:
            share = (day - left).days / (right - left).days
            return left_kc + (right_kc - left_kc) * share
    # Only reachable on a boundary shared by zero-length stages at the season end.
    return nodes[-1][1]


def to_contract(crop: CatalogCrop) -> Crop:
    """The crop in the shape of the API contract."""
    return Crop(
        id=crop.id,
        name=crop.name,
        name_genitive=crop.name_genitive,
        tile=crop.tile,
        season=crop.season,
        critical_period=crop.critical_period,
    )


def contract_crops() -> list[Crop]:
    return [to_contract(crop) for crop in CROPS]
