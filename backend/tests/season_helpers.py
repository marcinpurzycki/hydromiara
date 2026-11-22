"""Helpers for the season tests: a made-up spring crop built from the catalogue models."""

from app.catalog.crop_model import CatalogCrop, CropGrowth, Sourced, StageDates
from app.contracts.catalog import MonthDay, YearlyPeriod

_TEST = "made up for the test"


def _md(month: int, day: int) -> MonthDay:
    return MonthDay(month=month, day=day)


def _period(start: tuple[int, int], end: tuple[int, int]) -> YearlyPeriod:
    return YearlyPeriod(start=_md(*start), end=_md(*end))


def spring_crop() -> CatalogCrop:
    """Sown 20 April, harvested 10 October, critical period 1 July - 20 August."""
    growth = CropGrowth(
        season=Sourced[YearlyPeriod](value=_period((4, 20), (10, 10)), provisional=_TEST),
        critical_period=Sourced[YearlyPeriod](
            value=_period((7, 1), (8, 20)), provisional=_TEST
        ),
        stages=Sourced[StageDates](
            value=StageDates(
                establishment_end=_md(5, 10),
                development_start=_md(5, 25),
                mid_start=_md(7, 1),
                late_start=_md(9, 1),
            ),
            provisional=_TEST,
        ),
        kc_ini=Sourced[float](value=0.3, provisional=_TEST),
        kc_mid=Sourced[float](value=1.2, provisional=_TEST),
        kc_end=Sourced[float](value=0.6, provisional=_TEST),
        root_depth_m=Sourced[tuple[float, float]](value=(1.0, 1.7), provisional=_TEST),
        depletion_fraction=Sourced[float](value=0.55, provisional=_TEST),
    )
    return CatalogCrop(
        id="spring_test_crop",
        name="Uprawa jara testowa",
        name_genitive="uprawy jarej testowej",
        tile=False,
        growth=growth,
    )


SPRING = spring_crop()
