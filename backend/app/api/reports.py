"""Reading a Report, and the routes that create Reports from an existing one.

Reading is real: the stored Report is returned exactly as written and nothing
is computed again. Deriving a Report and the critical-period analysis are
still placeholders: they work for the fixed example report only and answer
"not available yet" for a Report of a real analysis instead of placeholder data.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.analyses import not_found, require_known_crop
from app.api.errors import ApiError, error_responses
from app.contracts.analyses import CriticalPeriodStarted, DerivedReport, DeriveRequest
from app.contracts.report import Report
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
    responses=error_responses(404, 425, 501),
    summary="Analiza na środek ostatniego Okresu krytycznego",
)
def critical_period(report_id: str) -> CriticalPeriodStarted:
    require_ready(report_id)
    return CriticalPeriodStarted(
        report_id=mock_store.start(), analysis_date=_MOCK_CRITICAL_PERIOD_DATE
    )
