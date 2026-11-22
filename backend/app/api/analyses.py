"""Starting an analysis, following its progress, supplying the crop history.

Analyses are real: the parcel and the weather are fetched and the engine runs.
Only the fixed example report and the stand-in reports created by the routes
that are still placeholders are answered from `app.mock`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.capacity import require_analysis_slot
from app.api.crop_history import require_valid_history
from app.api.errors import ApiError, error_responses
from app.api.validation import ReportId, require_analysis_date, require_parcel_id
from app.catalog.crops import has_crop
from app.contracts.analyses import AnalysisRequest, AnalysisStarted, AnalysisStatus, CropHistory
from app.mock import store as mock_store
from app.orchestrator import runtime
from app.orchestrator.service import Orchestrator
from app.orchestrator.sources import AnalysisSources, get_analysis_sources

router = APIRouter(prefix="/analyses", tags=["analyses"])

Service = Annotated[Orchestrator, Depends(runtime.get_orchestrator)]
Sources = Annotated[AnalysisSources, Depends(get_analysis_sources)]


def require_known_crop(crop_id: str) -> None:
    """Raise unless the crop is on the closed list (every listed crop can be analysed)."""
    if not has_crop(crop_id):
        raise ApiError(422, "unknown_crop", "Nieznana uprawa. Wybierz uprawę z listy.")


# The crop list of the API is the catalogue itself, so both checks are one.
require_catalog_crop = require_known_crop


def not_found() -> ApiError:
    return ApiError(404, "report_not_found", "Nie ma takiego raportu.")


@router.post(
    "",
    status_code=202,
    response_model=AnalysisStarted,
    responses=error_responses(422, 429, 503),
    summary="Start analizy",
    dependencies=[Depends(require_analysis_slot)],
)
async def start(request: AnalysisRequest, service: Service, sources: Sources) -> AnalysisStarted:
    require_catalog_crop(request.crop_id)
    require_parcel_id(request.parcel_id)
    require_analysis_date(request.analysis_date, runtime.local_today())
    # Whether the parcel exists is checked in the background, so that the
    # identifier returns at once; a missing parcel ends the analysis as failed.
    return AnalysisStarted(report_id=await service.start(request, sources))


@router.get(
    "/{report_id}/status",
    response_model=AnalysisStatus,
    responses=error_responses(404),
    summary="Postęp analizy i stan każdego źródła",
)
async def status(report_id: ReportId, service: Service) -> AnalysisStatus:
    if mock_store.exists(report_id):
        return mock_store.status(report_id)
    found = await service.status(report_id)
    if found is None:
        raise not_found()
    return found


@router.put(
    "/{report_id}/crop-history",
    status_code=204,
    response_class=Response,
    responses=error_responses(404, 409, 422),
    summary="Historia upraw podana w trakcie analizy",
)
async def put_crop_history(report_id: ReportId, history: CropHistory, service: Service) -> Response:
    if mock_store.exists(report_id):
        for crop_id in (history.years or {}).values():
            require_known_crop(crop_id)
        accepted = not mock_store.is_done(report_id)
    else:
        record = await service.record(report_id)
        if record is None:
            raise not_found()
        # A finished analysis answers "too late" whatever the history says.
        accepted = not record.finished
        if accepted:
            require_valid_history(history, record.crop_id, record.analysis_date)
            accepted = await service.put_crop_history(report_id, history)
    if not accepted:
        raise ApiError(
            409,
            "analysis_finished",
            "Analiza już się zakończyła. Historię upraw można dodać, tworząc nowy raport.",
        )
    return Response(status_code=204)
