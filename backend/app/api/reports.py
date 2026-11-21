"""Reading a Report and creating Reports derived from it. Placeholder implementation."""

from datetime import date

from fastapi import APIRouter

from app.api.analyses import require_analysis, require_known_crop
from app.api.errors import ApiError, error_responses
from app.contracts.analyses import CriticalPeriodStarted, DerivedReport, DeriveRequest
from app.contracts.report import Report
from app.mock import data, store

router = APIRouter(prefix="/reports", tags=["reports"])

# Placeholder: middle of the critical period of the fixed report.
_MOCK_CRITICAL_PERIOD_DATE = date(2023, 6, 7)


def require_ready(report_id: str) -> None:
    require_analysis(report_id)
    if not store.is_done(report_id):
        raise ApiError(425, "report_not_ready", "Raport jest jeszcze przygotowywany.")


@router.get(
    "/{report_id}",
    response_model=Report,
    responses=error_responses(404, 425),
    summary="Gotowy Raport",
)
def get_report(report_id: str) -> Report:
    require_ready(report_id)
    return data.report_for(report_id)


@router.post(
    "/{report_id}/derive",
    status_code=201,
    response_model=DerivedReport,
    responses=error_responses(404, 422, 425),
    summary="Nowy Raport z tych samych danych źródłowych i podanej Historii upraw",
)
def derive(report_id: str, request: DeriveRequest) -> DerivedReport:
    require_ready(report_id)
    for crop_id in (request.crop_history.years or {}).values():
        require_known_crop(crop_id)
    return DerivedReport(report_id=store.start(finished=True))


@router.post(
    "/{report_id}/critical-period",
    status_code=202,
    response_model=CriticalPeriodStarted,
    responses=error_responses(404, 425),
    summary="Analiza na środek ostatniego Okresu krytycznego",
)
def critical_period(report_id: str) -> CriticalPeriodStarted:
    require_ready(report_id)
    return CriticalPeriodStarted(
        report_id=store.start(), analysis_date=_MOCK_CRITICAL_PERIOD_DATE
    )
