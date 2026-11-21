"""Starting an analysis and following its progress. Placeholder implementation."""

from fastapi import APIRouter, Response

from app.api.errors import ApiError, error_responses
from app.contracts.analyses import AnalysisRequest, AnalysisStarted, AnalysisStatus, CropHistory
from app.mock import data, store

router = APIRouter(prefix="/analyses", tags=["analyses"])


def require_known_crop(crop_id: str) -> None:
    if crop_id not in {crop.id for crop in data.catalog().crops}:
        raise ApiError(422, "unknown_crop", "Nieznana uprawa. Wybierz uprawę z listy.")


def require_analysis(report_id: str) -> None:
    if not store.exists(report_id):
        raise ApiError(404, "report_not_found", "Nie ma takiego raportu.")


@router.post(
    "",
    status_code=202,
    response_model=AnalysisStarted,
    responses=error_responses(422),
    summary="Start analizy",
)
def start(request: AnalysisRequest) -> AnalysisStarted:
    require_known_crop(request.crop_id)
    return AnalysisStarted(report_id=store.start())


@router.get(
    "/{report_id}/status",
    response_model=AnalysisStatus,
    responses=error_responses(404),
    summary="Postęp analizy i stan każdego źródła",
)
def status(report_id: str) -> AnalysisStatus:
    require_analysis(report_id)
    return store.status(report_id)


@router.put(
    "/{report_id}/crop-history",
    status_code=204,
    response_class=Response,
    responses=error_responses(404, 409, 422),
    summary="Historia upraw podana w trakcie analizy",
)
def put_crop_history(report_id: str, history: CropHistory) -> Response:
    require_analysis(report_id)
    for crop_id in (history.years or {}).values():
        require_known_crop(crop_id)
    if store.is_done(report_id):
        raise ApiError(
            409,
            "analysis_finished",
            "Analiza już się zakończyła. Historię upraw można dodać, tworząc nowy raport.",
        )
    return Response(status_code=204)
