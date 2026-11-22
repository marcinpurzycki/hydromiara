"""Report parts about the deficit causes, their recommendations and the terrain.

Runs the terrain analysis, the cause checks and the recommendation rules of
the engine once and keeps their results together: the cause sections with
their recommendations, the downhill direction, the water objects and the water
retention sites for the map, the trace entries and the limitations.

The waters around the parcel are analysed from the stored water data. A water
retention site appears on the map only with a triggered recommendation that
points to it.

Irrigation recommendations are not placed in the cause sections; they are
kept apart for the irrigation part of the Report, which stands at its end.

The contract has no field for the sentence that explains an empty cause list
(no deficit, or verdicts without a level), so it is carried by a limitation
marked as affecting the recommendations and by the trace.
"""

from dataclasses import dataclass

from app.catalog.crop_model import CatalogCrop
from app.contracts.causes import Cause, RetentionSite
from app.contracts.report import DownhillDirection, Limitation, TraceEntry, WaterObject
from app.contracts.source_data import SourceData
from app.engine.assessment import WaterAssessment
from app.engine.cause_model import SourceNames
from app.engine.cause_params import DEFAULT_CAUSE_PARAMS, CauseParams
from app.engine.causes import CausesOutcome, deficit_causes
from app.engine.rule_facts import rule_facts
from app.engine.rules import Placed, recommend
from app.engine.terrain_analysis import TerrainAnalysis, analyse_terrain
from app.engine.terrain_report import downhill_direction, terrain_limitations, terrain_trace
from app.engine.water_analysis import analyse_waters
from app.engine.water_report import water_trace
from app.orchestrator.report_sources import report_source


@dataclass(frozen=True)
class CausesPart:
    outcome: CausesOutcome
    terrain: TerrainAnalysis | None
    causes: list[Cause]
    downhill_direction: DownhillDirection | None
    limitations: tuple[Limitation, ...]
    trace: list[TraceEntry]
    # Triggered irrigation entries with the cause each answers.
    irrigation: tuple[Placed, ...] = ()
    # For the map: sites of the triggered recommendations and the stored waters.
    retention_sites: tuple[RetentionSite, ...] = ()
    water_objects: tuple[WaterObject, ...] = ()


def source_names(source_data: SourceData) -> SourceNames:
    """Names of the sources that delivered the data, as listed in the Report."""
    names = {
        outcome.topic: report_source(outcome).name
        for outcome in source_data.outcomes
        if outcome.ok
    }
    default = SourceNames()
    return SourceNames(
        weather=names.get("weather", default.weather),
        soil=names.get("soil", default.soil),
        terrain=names.get("terrain", default.terrain),
    )


def causes_part(
    source_data: SourceData,
    assessment: WaterAssessment,
    crop: CatalogCrop,
    params: CauseParams = DEFAULT_CAUSE_PARAMS,
) -> CausesPart:
    terrain = None
    if source_data.terrain is not None:
        terrain = analyse_terrain(source_data.terrain, source_data.parcel.geometry, params)
    outcome = deficit_causes(assessment, crop, terrain, params, source_names(source_data))
    limitations = terrain_limitations(source_data, terrain, params)
    if outcome.statement is not None:
        limitations.insert(
            0, Limitation(text=outcome.statement, affects="recommendations", permanent=False)
        )
    hydro = source_data.hydro
    water = None if hydro is None else analyse_waters(hydro, source_data.parcel.geometry, terrain)
    facts = rule_facts(assessment, crop, terrain, water=water)
    sites = {} if water is None or water.site is None else {"water_object": water.site}
    rules = recommend(outcome, facts, sites=sites)
    limitations.extend(rules.limitations)
    trace = [*outcome.trace(), *rules.trace]
    if water is not None:
        trace.insert(0, water_trace(water))
    if terrain is not None:
        trace.insert(0, terrain_trace(terrain, params))
    used_sites = {
        item.recommendation.retention_site.id: item.recommendation.retention_site
        for item in rules.placed
        if item.recommendation.retention_site is not None
    }
    return CausesPart(
        outcome=outcome,
        terrain=terrain,
        causes=outcome.causes(rules.by_cause),
        downhill_direction=downhill_direction(terrain),
        limitations=tuple(limitations),
        trace=trace,
        irrigation=rules.irrigation,
        retention_sites=tuple(used_sites.values()),
        water_objects=tuple(
            WaterObject(kind=item.kind, name=item.name, geometry=item.geometry)
            for item in (hydro.objects if hydro is not None else ())
        ),
    )
