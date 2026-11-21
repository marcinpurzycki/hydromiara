"""Starting an analysis, following its progress, supplying the crop history.

Analyses are real: the parcel and the weather are fetched and the engine runs.
Only the fixed example report and the stand-in reports created by the routes
that are still placeholders are answered from `app.mock`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.errors import ApiError, error_responses
from app.catalog.crops import has_crop, list_crops
from app.contracts.analyses import AnalysisRequest, AnalysisStarted, AnalysisStatus, CropHistory
from app.mock import data
from app.mock import store as mock_store
from app.orchestrator import runtime
from app.orchestrator.service import Orchestrator
from app.orchestrator.sources import AnalysisSources, get_analysis_sources
from app.sources.parcel_query import is_parcel_id

router = APIRouter(prefix="/analyses", tags=["analyses"])

Service = Annotated[Orchestrator, Depends(runtime.get_orchestrator)]
Sources = Annotated[AnalysisSources, Depends(get_analysis_sources)]


def require_known_crop(crop_id: str) -> None:
    """Crop of the placeholder list; used only by routes that are still placeholders."""
    if crop_id not in {crop.id for crop in data.catalog().crops}:
        raise ApiError(422, "unknown_crop", "Nieznana uprawa. Wybierz uprawę z listy.")


def require_catalog_crop(crop_id: str) -> None:
    """Crop the engine has parameters for; anything else cannot be analysed."""
    if not has_crop(crop_id):
        available = ", ".join(crop.name for crop in list_crops())
        raise ApiError(
            422,
            "unknown_crop",
            f"Dla tej uprawy analiza nie jest dostępna. Dostępne uprawy: {available}.",
        )


def not_found() -> ApiError:
    return ApiError(404, "report_not_found", "Nie ma takiego raportu.")


@router.post(
    "",
    status_code=202,
    response_model=AnalysisStarted,
    responses=error_responses(422),
    summary="Start analizy",
)
async def start(request: AnalysisRequest, service: Service, sources: Sources) -> AnalysisStarted:
    require_catalog_crop(request.crop_id)
    if not is_parcel_id(request.parcel_id):
        raise ApiError(
            422,
            "invalid_parcel_id",
            "Podaj pełny identyfikator działki, np. 040704_2.0020.34/2.",
        )
    if request.analysis_date > runtime.local_today():
        raise ApiError(
            422, "analysis_date_in_future", "Data analizy nie może być późniejsza niż dzisiejsza."
        )
    # Whether the parcel exists is checked in the background, so that the
    # identifier returns at once; a missing parcel ends the analysis as failed.
    return AnalysisStarted(report_id=await service.start(request, sources))


@router.get(
    "/{report_id}/status",
    response_model=AnalysisStatus,
    responses=error_responses(404),
    summary="Postęp analizy i stan każdego źródła",
)
async def status(report_id: str, service: Service) -> AnalysisStatus:
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
async def put_crop_history(report_id: str, history: CropHistory, service: Service) -> Response:
    is_mock = mock_store.exists(report_id)
    for crop_id in (history.years or {}).values():
        (require_known_crop if is_mock else require_catalog_crop)(crop_id)
    if is_mock:
        accepted = not mock_store.is_done(report_id)
    else:
        accepted = await service.put_crop_history(report_id, history)
        if not accepted and await service.record(report_id) is None:
            raise not_found()
    if not accepted:
        raise ApiError(
            409,
            "analysis_finished",
            "Analiza już się zakończyła. Historię upraw można dodać, tworząc nowy raport.",
        )
    return Response(status_code=204)
