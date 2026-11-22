"""Simulation: multi-year susceptibility of other crops on the same parcel.

Pure: no network, clock or database. Every crop is assessed by the same entry
point, on the same weather and soil and with the same parameters as the Report
(`assess_water`), so the result for the current crop is the verdict of the
Report itself. Only the water balance is used: no satellite data, no crop
history, no consistency check, and nothing about yield or profitability.

What differs between crops is exactly what the balance takes from the crop
catalogue: the crop coefficient curve, the root zone (depth and depletion
fraction) and the critical period, which also sets the years of the window.

Rules of the ranking:
- The current crop is always returned next to the ranking and is never part
  of it; the ranking holds the other crops.
- A crop without a verdict (the field without a crop, or no weather in any of
  its critical periods) is not ranked; it is returned in `not_compared`.
- Order: the share of deficit years among the assessed years, lowest first.
  With the same number of assessed years this is the order of the numbers of
  deficit years. The share is used because crops may have different numbers
  of assessed years (their critical periods fall on different days, so a gap
  in the weather may cost one of them a year).
- Ties: fewer stress days in the critical periods per assessed year (the
  quantity already counted for every year of the window), then the order of
  the crop list. Both shares are exact fractions, so no rounding decides.

Rules of the year-by-year comparison: a year is listed when both crops have an
assessed critical period that began in it; other years are left out, because
"no assessment" is neither a deficit nor its absence. A year is partial when
the critical period of either crop was still running on the analysis date.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import list_crops
from app.contracts.source_data import SourceData
from app.engine.assessment import assess_water
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.susceptibility import SusceptibilityVerdict

# The ranking shows this many crops (definition of the ranking, not a tuned value).
TOP_COUNT: int = 3


@dataclass(frozen=True)
class CropResult:
    """Multi-year susceptibility of one crop on the parcel of the Report."""

    crop: CatalogCrop
    verdict: SusceptibilityVerdict

    @property
    def assessed(self) -> bool:
        return self.verdict.assessed

    @property
    def deficit_share(self) -> Fraction:
        """Deficit years among the assessed years; only for an assessed crop."""
        return Fraction(self.verdict.deficit_years, self.verdict.total_years)

    @property
    def stress_days_per_year(self) -> Fraction:
        """Stress days in the critical periods per assessed year; only for an assessed crop."""
        days = sum(year.stress_days for year in self.verdict.years if year.assessed)
        return Fraction(days, self.verdict.total_years)


@dataclass(frozen=True)
class ComparedYear:
    """One year in which both compared crops were assessed."""

    year: int
    current_deficit: bool
    other_deficit: bool
    partial: bool


@dataclass(frozen=True)
class Simulation:
    current: CropResult
    # Other crops with a verdict, least exposed to water deficit first.
    ranked: tuple[CropResult, ...]
    # Other crops without a verdict, in the order of the crop list.
    not_compared: tuple[CropResult, ...]

    @property
    def top(self) -> tuple[CropResult, ...]:
        """At most `TOP_COUNT` other crops; fewer when the list has fewer."""
        return self.ranked[:TOP_COUNT]

    def other(self, crop_id: str) -> CropResult | None:
        """The result of another crop, ranked or not; None when it was not simulated."""
        for result in (*self.ranked, *self.not_compared):
            if result.crop.id == crop_id:
                return result
        return None


def assess_crop(
    source_data: SourceData,
    crop: CatalogCrop,
    analysis_date: date,
    params: EngineParams = DEFAULT_PARAMS,
) -> CropResult:
    """Multi-year susceptibility of the crop, computed exactly as for a Report."""
    assessment = assess_water(source_data, crop, analysis_date, params)
    return CropResult(crop=crop, verdict=assessment.multiyear_susceptibility)


def simulate(
    source_data: SourceData,
    current: CatalogCrop,
    analysis_date: date,
    crops: Sequence[CatalogCrop] | None = None,
    params: EngineParams = DEFAULT_PARAMS,
) -> Simulation:
    """Susceptibility of the current crop and of every other crop of `crops`.

    `crops` defaults to the whole crop list; the current crop is recognised in
    it by its identifier and assessed once.
    """
    listed = list_crops() if crops is None else crops
    ranked: list[tuple[Fraction, Fraction, int, CropResult]] = []
    not_compared: list[CropResult] = []
    seen = {current.id}
    for position, crop in enumerate(listed):
        if crop.id in seen:
            continue
        seen.add(crop.id)
        result = assess_crop(source_data, crop, analysis_date, params)
        if result.assessed:
            ranked.append((result.deficit_share, result.stress_days_per_year, position, result))
        else:
            not_compared.append(result)
    ranked.sort(key=lambda entry: entry[:3])
    return Simulation(
        current=assess_crop(source_data, current, analysis_date, params),
        ranked=tuple(entry[3] for entry in ranked),
        not_compared=tuple(not_compared),
    )


def compare_years(current: CropResult, other: CropResult) -> tuple[ComparedYear, ...]:
    """Year by year, oldest first: the years in which both crops were assessed."""
    others = {year.year: year for year in other.verdict.years if year.assessed}
    compared = []
    for year in current.verdict.years:
        match = others.get(year.year)
        if not year.assessed or match is None:
            continue
        compared.append(
            ComparedYear(
                year=year.year,
                current_deficit=year.deficit,
                other_deficit=match.deficit,
                partial=year.partial or match.partial,
            )
        )
    return tuple(compared)
