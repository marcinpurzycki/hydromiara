"""Assembling the Report from stored inputs. Pure: no network, clock or randomness.

The same inputs always give the same Report, so a Report can be computed again
from what is stored with it. The identifier and the creation time are inputs.

The summary is the template one, made from the finished Report itself; asking
a language model for another wording is a step of the orchestrator, not of this
function.

The limitations and the confidence of both verdicts come from the engine: the
limitations are collected once and the confidence is derived from them. The
consistency check is made first, because its result is one of the limitations.
"""

from dataclasses import dataclass
from datetime import date, datetime

from app.catalog.crop_model import CatalogCrop
from app.contracts.analyses import CropHistory
from app.contracts.report import (
    Limitation,
    Report,
    ReportMap,
    ReportMeta,
    ReportParcel,
    Summary,
)
from app.contracts.source_data import SourceData
from app.contracts.verdicts import CropRef
from app.engine import history_texts, season_store, season_texts
from app.engine.assessment import assess_water
from app.engine.confidence import verdict_confidences
from app.engine.consistency import check_consistency
from app.engine.history import historical_course
from app.engine.irrigation import assess_irrigation
from app.engine.limitations import limitations_of, report_findings
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.season import critical_period_date, past_season, season_status
from app.orchestrator import report_sources as sources
from app.orchestrator import report_verdicts as verdicts
from app.orchestrator.report_causes import causes_part
from app.summary.template import template_summary

_PARCEL_FIELDS = {"parcel_id", "number", "region", "commune", "county", "voivodeship", "area_ha"}


@dataclass(frozen=True)
class ReportInputs:
    report_id: str
    created_at: datetime
    source_data: SourceData
    crop: CatalogCrop
    analysis_date: date
    # Read only by the historical course and the assumption sentence next to
    # the susceptibility; no verdict, cause or recommendation depends on it.
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
    status = season_status(crop, analysis_date)
    current = assessment.current_status
    past = past_season(assessment.balance, crop, status) if status.store_assessed else None
    causes = causes_part(source_data, assessment, crop)
    irrigation = assess_irrigation(assessment, crop, status)
    susceptibility = assessment.multiyear_susceptibility
    course = historical_course(source_data, assessment, crop, inputs.crop_history, params)

    consistency = check_consistency(
        source_data, assessment, crop, analysis_date, crop_history=inputs.crop_history
    )

    not_assessed = verdicts.not_assessed_limitation(assessment)
    findings = report_findings(
        source_data,
        assessment,
        source_limitations=inputs.source_limitations,
        consistency=consistency.result,
        consistency_affects=consistency.affects,
        consistency_gaps=consistency.findings,
        replaced_missing=consistency.replaces_missing,
        first=() if not_assessed is None else (not_assessed,),
        last=causes.limitations,
    )
    confidence = verdict_confidences(
        findings,
        current_not_assessed=verdicts.not_assessed_sentence(assessment.current_status),
        multiyear_not_assessed=verdicts.not_assessed_sentence(
            assessment.multiyear_susceptibility
        ),
    )
    report = Report(
        meta=_meta(inputs),
        headline=verdicts.headline(
            assessment,
            analysis_date,
            season_texts.headline_sentence(status, analysis_date, current),
        ),
        # Replaced below: the summary is made from the finished Report.
        summary=Summary(text="", source="template"),
        season=season_texts.season_section(crop, status, analysis_date),
        current_status=season_store.current_status(
            verdicts.current_status(assessment, confidence.current),
            crop, status, analysis_date, current, past,
        ),
        multiyear_susceptibility=verdicts.multiyear_susceptibility(
            assessment, crop, confidence.multiyear, course
        ),
        historical_course=(
            None if course is None else history_texts.course_section(course, susceptibility, crop)
        ),
        causes=causes.causes,
        irrigation=irrigation.section,
        consistency_check=consistency.check,
        sources=sources.report_sources(source_data),
        limitations=limitations_of(findings),
        map=ReportMap(
            parcel_geometry=source_data.parcel.geometry,
            downhill_direction=causes.downhill_direction,
            retention_sites=list(causes.retention_sites),
            water_objects=list(causes.water_objects),
        ),
        trace=[
            *verdicts.trace(assessment, params),
            season_texts.trace_entry(status, critical_period_date(crop, analysis_date)),
            *causes.trace,
            irrigation.trace,
            consistency.trace,
            *([] if course is None else [history_texts.trace_entry(course, susceptibility)]),
        ],
    )
    return report.model_copy(update={"summary": template_summary(report)})
