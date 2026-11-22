"""Parcel facts for the recommendation rules, derived from results already computed.

Nothing is measured or decided here: each fact repeats a value of the water
assessment, of the crop catalogue or of the terrain analysis, rounded as it is
shown in the Report, so a recommendation never quotes a value the Report
does not have.

A data topic is available when its data exist for the parcel. Facts of a
missing topic are absent; a fact of an available topic may still be unknown
(None), for example the lowest part of a parcel that is flat within what the
terrain grid can show.

Pure: no network, clock or files.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.catalog.crop_model import CatalogCrop
from app.catalog.recommendation_facts import DataTopic
from app.contracts.catalog import MonthDay
from app.contracts.common import Scalar
from app.engine.assessment import WaterAssessment
from app.engine.season import season_status
from app.engine.terrain_analysis import TerrainAnalysis
from app.engine.water_analysis import WaterAnalysis
from app.engine.water_report import water_facts


@dataclass(frozen=True)
class RuleFacts:
    values: Mapping[str, Scalar] = field(default_factory=dict)
    available: frozenset[DataTopic] = frozenset()

    def get(self, name: str) -> Scalar:
        """The value of a fact; None when it is unknown or its topic has no data."""
        return self.values.get(name)


def _day(moment: MonthDay) -> str:
    return f"{moment.day:02d}.{moment.month:02d}"


def _balance_facts(assessment: WaterAssessment) -> dict[str, Scalar]:
    current, multiyear = assessment.current_status, assessment.multiyear_susceptibility
    stress = current.stress_coefficient
    assessed = multiyear.deficit_level is not None
    return {
        "current_deficit_level": current.deficit_level,
        "current_label": current.label,
        "stress_coefficient": None if stress is None else round(stress, 2),
        "multiyear_deficit_level": multiyear.deficit_level,
        "multiyear_label": multiyear.label,
        "deficit_years": multiyear.deficit_years if assessed else None,
        "total_years": multiyear.total_years if assessed else None,
    }


def _crop_facts(assessment: WaterAssessment, crop: CatalogCrop) -> dict[str, Scalar]:
    critical = crop.critical_period
    status = season_status(crop, assessment.analysis_date)
    return {
        "crop_name": crop.name,
        "crop_name_genitive": crop.name_genitive,
        "crop_perennial": crop.perennial,
        "harvest_by_august_end": crop.season is not None and crop.season.end.month <= 8,
        # A dormant winter crop is in its season; the two facts tell them apart.
        "in_season": status.in_season,
        "dormant": status.state == "dormant",
        "critical_period_start": None if critical is None else _day(critical.start),
        "critical_period_end": None if critical is None else _day(critical.end),
    }


def _terrain_facts(terrain: TerrainAnalysis) -> dict[str, Scalar]:
    slope = terrain.slope_pct
    return {
        "slope_pct": None if slope is None else round(slope, 1),
        "downhill_label": terrain.downhill_label,
        "lowest_part": terrain.lowest_part,
    }


def rule_facts(
    assessment: WaterAssessment,
    crop: CatalogCrop,
    terrain: TerrainAnalysis | None,
    *,
    water: WaterAnalysis | None = None,
    water_available: bool = False,
) -> RuleFacts:
    """Facts of one analysis; `terrain` is None without terrain data.

    `water` is the analysis of the waters around the parcel; None without
    water data. `water_available` alone marks the data as present without
    giving any fact of them.
    """
    values = _balance_facts(assessment)
    available: set[DataTopic] = {"balance"}
    if not crop.is_bare_field:
        values |= _crop_facts(assessment, crop)
        available.add("crop")
    zone = assessment.root_zone
    # A stand-in capacity says nothing about the soil of this parcel.
    if zone.capacity_source != "fallback":
        values["available_water_mm_per_m"] = float(round(zone.available_water_mm_per_m))
        available.add("soil")
    if terrain is not None and terrain.analysed:
        values |= _terrain_facts(terrain)
        available.add("terrain")
    if water is not None:
        values |= water_facts(water)
    if water is not None or water_available:
        available.add("water")
    return RuleFacts(values=values, available=frozenset(available))
