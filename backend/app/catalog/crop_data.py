"""Crop catalogue data. Adding or correcting a crop is a change of this file only.

Every value names its source (document and table). A value without a
scientific source carries a `provisional` reason and a PROVISIONAL comment.
A crop enters the list only with the complete set of parameters.
"""

from app.catalog.crop_model import CatalogCrop, CropGrowth, Sourced, StageDates
from app.contracts.catalog import MonthDay, YearlyPeriod

FAO56 = (
    "Allen R.G., Pereira L.S., Raes D., Smith M. (1998). Crop evapotranspiration: "
    "guidelines for computing crop water requirements. "
    "FAO Irrigation and Drainage Paper 56"
)
FAO56_TABLE_12 = f"{FAO56}, Table 12 (single crop coefficients Kc)"
FAO56_TABLE_22 = f"{FAO56}, Table 22 (maximum effective rooting depth Zr, depletion fraction p)"

_TRIAL = "taken from the trial calculation of this project"


def _period(start: tuple[int, int], end: tuple[int, int]) -> YearlyPeriod:
    return YearlyPeriod(
        start=MonthDay(month=start[0], day=start[1]),
        end=MonthDay(month=end[0], day=end[1]),
    )


def _day(month: int, day: int) -> MonthDay:
    return MonthDay(month=month, day=day)


# PROVISIONAL: crop coefficient of a field without plants (bare soil), used for
# the field without a crop and for every crop outside its season. FAO-56 gives
# no single tabulated value (it depends on how often the soil is wetted).
BARE_SOIL_KC: Sourced[float] = Sourced[float](
    value=0.3,
    provisional=f"bare-soil Kc has no tabulated source; {_TRIAL}",
)

WINTER_WHEAT = CatalogCrop(
    id="winter_wheat",
    name="Pszenica ozima",
    name_genitive="pszenicy ozimej",
    tile=True,
    growth=CropGrowth(
        # PROVISIONAL: sowing and harvest dates for Poland have no source yet.
        season=Sourced[YearlyPeriod](
            value=_period((9, 25), (7, 31)),
            provisional=f"sowing and harvest dates for Poland; {_TRIAL}",
        ),
        # PROVISIONAL: critical period 15 May - 30 June has no source yet.
        critical_period=Sourced[YearlyPeriod](
            value=_period((5, 15), (6, 30)),
            provisional="working value without a source",
        ),
        # PROVISIONAL: stage dates for Poland have no source yet; FAO-56
        # Table 11 has no stage lengths for Central Europe.
        stages=Sourced[StageDates](
            value=StageDates(
                establishment_end=_day(10, 27),
                development_start=_day(3, 16),
                mid_start=_day(5, 5),
                late_start=_day(6, 30),
            ),
            provisional=f"growth stage dates for Poland; {_TRIAL}",
        ),
        # PROVISIONAL: the table gives 0.4 for frozen soils and 0.7 otherwise;
        # taking the frozen-soil variant for Poland is an assumption.
        kc_ini=Sourced[float](
            value=0.4,
            source=f"{FAO56_TABLE_12}: winter wheat, with frozen soils",
            provisional="choice of the frozen-soil variant (0.4) over 0.7 is an assumption",
        ),
        kc_mid=Sourced[float](value=1.15, source=f"{FAO56_TABLE_12}: winter wheat"),
        # PROVISIONAL: the table gives the range 0.25-0.40; the value inside it
        # has no source yet.
        kc_end=Sourced[float](
            value=0.3,
            source=f"{FAO56_TABLE_12}: winter wheat, range 0.25-0.40",
            provisional=f"value chosen inside the tabulated range; {_TRIAL}",
        ),
        root_depth_m=Sourced[tuple[float, float]](
            value=(1.5, 1.8), source=f"{FAO56_TABLE_22}: winter wheat"
        ),
        depletion_fraction=Sourced[float](
            value=0.55, source=f"{FAO56_TABLE_22}: winter wheat"
        ),
    ),
)

BARE_FIELD = CatalogCrop(
    id="bare_field",
    name="Pole bez uprawy",
    name_genitive="pola bez uprawy",
    tile=True,
    growth=None,
)

# Order of the list shown to the user.
CROPS: tuple[CatalogCrop, ...] = (WINTER_WHEAT, BARE_FIELD)
