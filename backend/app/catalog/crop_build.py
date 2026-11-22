"""Builds a catalogue entry from the compact form used by the crop data files.

The data files give dates as "MM-DD" texts and one source text per group of
values; this module turns them into the catalogue model, where every single
value carries its source and, when it has one, its provisional reason.
"""

from collections.abc import Mapping

from app.catalog.crop_model import CatalogCrop, CropGrowth, Sourced, StageDates
from app.catalog.crop_sources import FAO56_TABLE_24, IUNG_GROUPS
from app.contracts.catalog import MonthDay, YearlyPeriod


def moment(text: str) -> MonthDay:
    """Month and day from a "MM-DD" text."""
    month, day = text.split("-")
    return MonthDay(month=int(month), day=int(day))


def period(start: str, end: str) -> YearlyPeriod:
    return YearlyPeriod(start=moment(start), end=moment(end))


def build_crop(
    *,
    id: str,
    name: str,
    name_genitive: str,
    season: tuple[str, str],
    stages: tuple[str, str, str, str],
    critical_period: tuple[str, str],
    kc: tuple[float, float, float],
    root_depth_m: tuple[float, float],
    depletion_fraction: float,
    dates_source: str,
    kc_source: str,
    root_source: str,
    critical_source: str,
    maturity: str | None = None,
    ky: float | None = None,
    drought_monitoring_group: str | None = None,
    tile: bool = False,
    conditional: bool = False,
    perennial: bool = False,
    note: str | None = None,
    provisional: Mapping[str, str] | None = None,
) -> CatalogCrop:
    """One growing crop.

    `season` is (sowing, harvest); `stages` is (establishment end, development
    start, mid-season start, late-season start); `kc` is (ini, mid, end).
    `provisional` maps a parameter name of `CropGrowth` to the reason why that
    value has no scientific source of its own.
    """
    reasons = dict(provisional or {})
    unknown = set(reasons) - set(CropGrowth.model_fields)
    if unknown:
        raise ValueError(f"unknown catalogue parameters: {sorted(unknown)}")

    def sourced(name: str, value: object, source: str) -> dict:
        return {"value": value, "source": source, "provisional": reasons.get(name)}

    stage_dates = StageDates(
        establishment_end=moment(stages[0]),
        development_start=moment(stages[1]),
        mid_start=moment(stages[2]),
        late_start=moment(stages[3]),
        maturity=None if maturity is None else moment(maturity),
    )
    growth = CropGrowth(
        season=Sourced[YearlyPeriod](**sourced("season", period(*season), dates_source)),
        critical_period=Sourced[YearlyPeriod](
            **sourced("critical_period", period(*critical_period), critical_source)
        ),
        stages=Sourced[StageDates](**sourced("stages", stage_dates, dates_source)),
        kc_ini=Sourced[float](**sourced("kc_ini", kc[0], kc_source)),
        kc_mid=Sourced[float](**sourced("kc_mid", kc[1], kc_source)),
        kc_end=Sourced[float](**sourced("kc_end", kc[2], kc_source)),
        root_depth_m=Sourced[tuple[float, float]](
            **sourced("root_depth_m", root_depth_m, root_source)
        ),
        depletion_fraction=Sourced[float](
            **sourced("depletion_fraction", depletion_fraction, root_source)
        ),
        yield_response_ky=(
            None
            if ky is None
            else Sourced[float](**sourced("yield_response_ky", ky, FAO56_TABLE_24))
        ),
        drought_monitoring_group=(
            None
            if drought_monitoring_group is None
            else Sourced[str](
                **sourced("drought_monitoring_group", drought_monitoring_group, IUNG_GROUPS)
            )
        ),
    )
    return CatalogCrop(
        id=id,
        name=name,
        name_genitive=name_genitive,
        tile=tile,
        growth=growth,
        conditional=conditional,
        perennial=perennial,
        note=note,
    )


def all_values(reason: str) -> dict[str, str]:
    """The same provisional reason for every parameter of a crop."""
    return dict.fromkeys(CropGrowth.model_fields, reason)
