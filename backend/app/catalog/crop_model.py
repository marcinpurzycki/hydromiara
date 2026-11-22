"""Model of a crop catalogue entry: every agronomic value carries its provenance."""

from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog.periods import cycle_offset, is_every_year
from app.contracts.catalog import MonthDay, YearlyPeriod

T = TypeVar("T")


class CatalogModel(BaseModel):
    """Base for catalogue models: immutable, unknown fields rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Sourced(CatalogModel, Generic[T]):
    """A value with its provenance.

    `source` names the document and table the value comes from. `provisional`
    says why the value (or the choice made within a sourced range) still has no
    scientific source. At least one of them is required; both may be given.
    """

    value: T
    source: str | None = None
    provisional: str | None = None

    @model_validator(mode="after")
    def _has_provenance(self) -> Self:
        if not (self.source or "").strip() and not (self.provisional or "").strip():
            raise ValueError("a catalogue value needs a source or a provisional reason")
        return self

    @property
    def is_provisional(self) -> bool:
        return self.provisional is not None


class StageDates(CatalogModel):
    """Dates that split the season into growth stages (FAO-56 crop coefficient curve).

    Sowing and harvest are the ends of the season itself. Between them:
    sowing -> establishment_end: Kc rises from the bare-soil value to Kc ini,
    establishment_end -> development_start: Kc ini (for a winter crop: dormancy),
    development_start -> mid_start: Kc rises linearly from Kc ini to Kc mid,
    mid_start -> late_start: Kc mid,
    late_start -> maturity: Kc falls linearly from Kc mid to Kc end,
    maturity -> harvest: Kc end.
    Without a maturity date the fall lasts until harvest.
    """

    establishment_end: MonthDay
    development_start: MonthDay
    mid_start: MonthDay
    late_start: MonthDay
    maturity: MonthDay | None = None


class CropGrowth(CatalogModel):
    """Water-related parameters of a crop that grows on the field."""

    season: Sourced[YearlyPeriod]
    critical_period: Sourced[YearlyPeriod]
    stages: Sourced[StageDates]
    kc_ini: Sourced[float]
    kc_mid: Sourced[float]
    kc_end: Sourced[float]
    # Range of the maximum effective rooting depth, metres.
    root_depth_m: Sourced[tuple[float, float]]
    # Fraction of available soil water that can be depleted before stress (p).
    depletion_fraction: Sourced[float]
    # Seasonal yield response factor Ky; None when the source has no row for the crop.
    yield_response_ky: Sourced[float] | None = None
    # Crop group of the national agricultural drought monitoring; None when it has none.
    drought_monitoring_group: Sourced[str] | None = None

    def sourced_values(self) -> dict[str, Sourced]:
        """Every given parameter by name, for completeness checks and reports."""
        values = {name: getattr(self, name) for name in type(self).model_fields}
        return {name: value for name, value in values.items() if value is not None}

    @model_validator(mode="after")
    def _is_consistent(self) -> Self:
        season = self.season.value
        critical = self.critical_period.value
        stages = self.stages.value
        moments = [season.start, season.end, critical.start, critical.end]
        moments += [stages.establishment_end, stages.development_start]
        moments += [stages.mid_start, stages.late_start]
        if stages.maturity is not None:
            moments.append(stages.maturity)
        if not all(is_every_year(moment) for moment in moments):
            raise ValueError("catalogue dates must exist in every year (no 29 February)")

        def offset(moment: MonthDay) -> int:
            return cycle_offset(season.start, moment)

        season_days = offset(season.end)
        if season_days == 0:
            raise ValueError("the season must be longer than one day")
        order = [
            0,
            offset(stages.establishment_end),
            offset(stages.development_start),
            offset(stages.mid_start),
            offset(stages.late_start),
            season_days if stages.maturity is None else offset(stages.maturity),
            season_days,
        ]
        if order != sorted(order):
            raise ValueError("growth stages must follow each other inside the season")
        if not offset(critical.start) <= offset(critical.end) <= season_days:
            raise ValueError("the critical period must lie inside the season")

        for name in ("kc_ini", "kc_mid", "kc_end"):
            if not 0 < getattr(self, name).value <= 2:
                raise ValueError(f"{name} must be a positive crop coefficient")
        shallow, deep = self.root_depth_m.value
        if not 0 < shallow <= deep:
            raise ValueError("root depth must be a positive, ordered range")
        if not 0 < self.depletion_fraction.value < 1:
            raise ValueError("the depletion fraction must lie between 0 and 1")
        if self.yield_response_ky is not None and self.yield_response_ky.value <= 0:
            raise ValueError("the yield response factor must be positive")
        return self


class CatalogCrop(CatalogModel):
    """One position of the closed crop list."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    name_genitive: str = Field(min_length=1)
    tile: bool
    # None for the field without a crop: nothing grows, only bare soil evaporates.
    growth: CropGrowth | None
    # True when part of the parameters is taken by analogy or as a working value;
    # the values concerned carry a `provisional` reason.
    conditional: bool = False
    # True for a plant that is not sown and harvested every year; its "season"
    # is the growing period, not the time from sowing to harvest.
    perennial: bool = False
    # Remark of the catalogue about the whole entry.
    note: str | None = None

    @property
    def is_bare_field(self) -> bool:
        return self.growth is None

    @property
    def season(self) -> YearlyPeriod | None:
        return None if self.growth is None else self.growth.season.value

    @property
    def critical_period(self) -> YearlyPeriod | None:
        return None if self.growth is None else self.growth.critical_period.value
