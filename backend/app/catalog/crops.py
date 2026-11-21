"""Closed crop list: lookup, crop coefficient curve, season and critical period.

Pure functions over the catalogue data: no network, no clock, no state. The
caller always passes the day it asks about.
"""

from datetime import date

from app.catalog.crop_data import BARE_SOIL_KC, CROPS
from app.catalog.crop_model import CatalogCrop
from app.catalog.periods import DateRange, last_occurrence, occurrence_containing, on_or_after
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


def kc(crop: CatalogCrop, day: date, *, bare_soil_kc: float | None = None) -> float:
    """Crop coefficient Kc of the crop on the given day.

    Inside the season the value follows the stage curve of the crop (flat
    stages joined by linear changes, counted in real days, so leap years are
    handled). Outside the season, and for the field without a crop, it is the
    bare-soil coefficient; `bare_soil_kc` overrides the catalogue value.
    """
    bare = BARE_SOIL_KC.value if bare_soil_kc is None else bare_soil_kc
    growth = crop.growth
    if growth is None:
        return bare
    season = occurrence_containing(growth.season.value, day)
    if season is None:
        return bare

    stages = growth.stages.value
    ini, mid, end = growth.kc_ini.value, growth.kc_mid.value, growth.kc_end.value
    nodes: list[tuple[date, float]] = [
        (season.start, bare),
        (on_or_after(stages.establishment_end, season.start), ini),
        (on_or_after(stages.development_start, season.start), ini),
        (on_or_after(stages.mid_start, season.start), mid),
        (on_or_after(stages.late_start, season.start), mid),
        (season.end, end),
    ]
    for (left, left_kc), (right, right_kc) in zip(nodes, nodes[1:]):
        if left < right and left <= day <= right:
            share = (day - left).days / (right - left).days
            return left_kc + (right_kc - left_kc) * share
    # Only reachable on a boundary shared by zero-length stages at the season end.
    return end


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
