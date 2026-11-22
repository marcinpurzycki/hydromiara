"""Reading a Report, and the routes that create Reports from an existing one.

Reading is real: the stored Report is returned exactly as written and nothing
is computed again. The critical-period route is real too: it starts an
ordinary analysis (new fetch of the data) of the same parcel and crop for the
middle day of the latest critical period that is not later than the analysis
date of the given Report; the given Report is never changed. Deriving a Report
is still a placeholder: it works for the fixed example report only and answers
"not available yet" for a Report of a real analysis instead of placeholder data.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.analyses import Sources, not_found, require_catalog_crop, require_known_crop
from app.api.errors import ApiError, error_responses
from app.catalog.crops import get_crop
from app.contracts.analyses import (
    AnalysisRequest,
    CriticalPeriodStarted,
    DerivedReport,
    DeriveRequest,
)
from app.contracts.report import Report
from app.engine.season import critical_period_date
from app.mock import data
from app.mock import store as mock_store
from app.orchestrator import runtime
from app.orchestrator.service import Orchestrator, utc_now
from app.storage.reports import AnalysisRecord

router = APIRouter(prefix="/reports", tags=["reports"])

Service = Annotated[Orchestrator, Depends(runtime.get_orchestrator)]

# Placeholder: middle of the critical period of the fixed report.
_MOCK_CRITICAL_PERIOD_DATE = date(2023, 6, 7)


def _not_ready() -> ApiError:
    return ApiError(425, "report_not_ready", "Raport jest jeszcze przygotowywany.")


def require_report(record: AnalysisRecord | None) -> None:
    """Raise unless the analysis ended with a Report."""
    if record is None:
        raise not_found()
    if not record.finished:
        raise _not_ready()
    if record.state == "failed":
        # No Report exists; the body says why the analysis failed.
        raise ApiError(404, record.error_code or "analysis_failed", record.error_message or "")


def require_ready(report_id: str) -> None:
    """Gate of the placeholder routes (also used by the simulation routes).

    Passes for the example report and its stand-ins. For a Report of a real
    analysis the placeholder data would be wrong, so the answer is an error.
    """
    if mock_store.exists(report_id):
        if not mock_store.is_done(report_id):
            raise _not_ready()
        return
    require_report(runtime.get_orchestrator().store.get(report_id, utc_now()))
    raise ApiError(
        501,
        "not_available_yet",
        "Ta funkcja nie jest jeszcze dostępna dla raportów z analizy; działa dla raportu "
        "przykładowego.",
    )


@router.get(
    "/{report_id}",
    response_model=Report,
    responses=error_responses(404, 425),
    summary="Gotowy Raport",
)
async def get_report(report_id: str, service: Service) -> Response | Report:
    if mock_store.exists(report_id):
        if not mock_store.is_done(report_id):
            raise _not_ready()
        return data.report_for(report_id)
    stored = await service.report_json(report_id)
    if stored is None:
        require_report(await service.record(report_id))
        raise _not_ready()
    return Response(content=stored, media_type="application/json")


@router.post(
    "/{report_id}/derive",
    status_code=201,
    response_model=DerivedReport,
    responses=error_responses(404, 422, 425, 501),
    summary="Nowy Raport z tych samych danych źródłowych i podanej Historii upraw",
)
def derive(report_id: str, request: DeriveRequest) -> DerivedReport:
    require_ready(report_id)
    for crop_id in (request.crop_history.years or {}).values():
        require_known_crop(crop_id)
    return DerivedReport(report_id=mock_store.start(finished=True))


@router.post(
    "/{report_id}/critical-period",
    status_code=202,
    response_model=CriticalPeriodStarted,
    responses=error_responses(404, 409, 422, 425),
    summary="Analiza na środek ostatniego Okresu krytycznego",
)
async def critical_period(
    report_id: str, service: Service, sources: Sources
) -> CriticalPeriodStarted:
    if mock_store.exists(report_id):
        if not mock_store.is_done(report_id):
            raise _not_ready()
        return CriticalPeriodStarted(
            report_id=mock_store.start(), analysis_date=_MOCK_CRITICAL_PERIOD_DATE
        )
    record = await service.record(report_id)
    require_report(record)
    require_catalog_crop(record.crop_id)
    target = critical_period_date(get_crop(record.crop_id), record.analysis_date)
    if target is None:
        raise ApiError(
            409,
            "no_critical_period",
            "Pole bez uprawy nie ma Okresu krytycznego, więc nie ma okresu największego "
            "zapotrzebowania na wodę, który można pokazać.",
        )
    if target == record.analysis_date:
        raise ApiError(
            409,
            "already_critical_period",
            f"Ten raport już dotyczy środka Okresu krytycznego ({target:%d.%m.%Y}).",
        )
    # The same path as an ordinary analysis; the new date is never later than
    # the date of the given Report, so it cannot lie in the future.
    request = AnalysisRequest(
        parcel_id=record.parcel_id, crop_id=record.crop_id, analysis_date=target
    )
    started = await service.start(request, sources, changed_from_date=record.analysis_date)
    return CriticalPeriodStarted(report_id=started, analysis_date=target)
