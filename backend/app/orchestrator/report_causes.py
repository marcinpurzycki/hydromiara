"""Report parts about the deficit causes and the terrain of the parcel.

Runs the terrain analysis and the cause checks of the engine once and keeps
their results together: the cause sections, the downhill direction for the
map, the trace entries and the limitations.

The contract has no field for the sentence that explains an empty cause list
(no deficit, or verdicts without a level), so it is carried by a limitation
marked as affecting the recommendations and by the trace.
"""

from dataclasses import dataclass

from app.catalog.crop_model import CatalogCrop
from app.contracts.causes import Cause
from app.contracts.report import DownhillDirection, Limitation, TraceEntry
from app.contracts.source_data import SourceData
from app.engine.assessment import WaterAssessment
from app.engine.cause_model import SourceNames
from app.engine.cause_params import DEFAULT_CAUSE_PARAMS, CauseParams
from app.engine.causes import CausesOutcome, deficit_causes
from app.engine.terrain_analysis import TerrainAnalysis, analyse_terrain
from app.engine.terrain_report import downhill_direction, terrain_limitations, terrain_trace
from app.orchestrator.report_sources import report_source


@dataclass(frozen=True)
class CausesPart:
    outcome: CausesOutcome
    terrain: TerrainAnalysis | None
    causes: list[Cause]
    downhill_direction: DownhillDirection | None
    limitations: tuple[Limitation, ...]
    trace: list[TraceEntry]


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
    trace = outcome.trace()
    if terrain is not None:
        trace.insert(0, terrain_trace(terrain, params))
    return CausesPart(
        outcome=outcome,
        terrain=terrain,
        causes=outcome.causes(),
        downhill_direction=downhill_direction(terrain),
        limitations=tuple(limitations),
        trace=trace,
    )
