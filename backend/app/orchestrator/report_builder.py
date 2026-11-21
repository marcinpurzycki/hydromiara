"""Assembling the Report from stored inputs. Pure: no network, clock or randomness.

The same inputs always give the same Report, so a Report can be computed again
from what is stored with it. The identifier and the creation time are inputs.

Adding a part of the Report: compute it in its own module from `ReportInputs`
and the engine assessment, and replace the matching `pending_*` call below.

The limitations and the confidence of both verdicts come from the engine: the
limitations are collected once and the confidence is derived from them. The
result of the consistency check, once it is made, is passed to
`report_findings` as `consistency`.
"""

from dataclasses import dataclass
from datetime import date, datetime

from app.catalog.crop_model import CatalogCrop
from app.contracts.analyses import CropHistory
from app.contracts.report import Limitation, Report, ReportMap, ReportMeta, ReportParcel
from app.contracts.source_data import SourceData
from app.contracts.verdicts import CropRef
from app.engine.assessment import assess_water
from app.engine.confidence import verdict_confidences
from app.engine.limitations import limitations_of, report_findings
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.orchestrator import report_pending as pending
from app.orchestrator import report_sources as sources
from app.orchestrator import report_verdicts as verdicts

_PARCEL_FIELDS = {"parcel_id", "number", "region", "commune", "county", "voivodeship", "area_ha"}


@dataclass(frozen=True)
class ReportInputs:
    report_id: str
    created_at: datetime
    source_data: SourceData
    crop: CatalogCrop
    analysis_date: date
    # Kept with the analysis; the historical course computed from it comes later.
    crop_history: CropHistory | None = None
    # Limitations the sources returned next to their data.
    source_limitations: tuple[Limitation, ...] = ()
    derived_from: str | None = None
    changed_from_date: date | None = None


def _meta(inputs: ReportInputs) -> ReportMeta:
    parcel = inputs.source_data.parcel
    return ReportMeta(
        report_id=inputs.report_id,
        created_at=inputs.created_at,
        parcel=ReportParcel.model_validate(parcel.model_dump(include=_PARCEL_FIELDS)),
        crop=CropRef(id=inputs.crop.id, name=inputs.crop.name),
        analysis_date=inputs.analysis_date,
        derived_from=inputs.derived_from,
        changed_from_date=inputs.changed_from_date,
    )


def build_report(inputs: ReportInputs, params: EngineParams = DEFAULT_PARAMS) -> Report:
    source_data, crop, analysis_date = inputs.source_data, inputs.crop, inputs.analysis_date
    assessment = assess_water(source_data, crop, analysis_date, params)
    season = verdicts.season(crop, analysis_date)

    not_assessed = verdicts.not_assessed_limitation(assessment)
    findings = report_findings(
        source_data,
        assessment,
        source_limitations=inputs.source_limitations,
        first=() if not_assessed is None else (not_assessed,),
        last=(pending.pending_limitation(),),
    )
    confidence = verdict_confidences(
        findings,
        current_not_assessed=verdicts.not_assessed_sentence(assessment.current_status),
        multiyear_not_assessed=verdicts.not_assessed_sentence(
            assessment.multiyear_susceptibility
        ),
    )
    return Report(
        meta=_meta(inputs),
        headline=verdicts.headline(assessment, analysis_date),
        summary=pending.pending_summary(),
        season=season,
        current_status=verdicts.current_status(assessment, confidence.current),
        multiyear_susceptibility=verdicts.multiyear_susceptibility(
            assessment, crop, confidence.multiyear
        ),
        historical_course=pending.pending_historical_course(),
        causes=pending.pending_causes(),
        irrigation=pending.pending_irrigation(season.in_season),
        consistency_check=pending.pending_consistency_check(),
        sources=sources.report_sources(source_data),
        limitations=limitations_of(findings),
        map=ReportMap(
            parcel_geometry=source_data.parcel.geometry,
            downhill_direction=None,
            retention_sites=[],
            water_objects=[],
        ),
        trace=verdicts.trace(assessment, params),
    )
