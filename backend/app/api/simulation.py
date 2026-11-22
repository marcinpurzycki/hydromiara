"""Simulation: crop ranking and year-by-year comparison for a stored Report.

Both routes compute from what is stored with the Report (weather and soil of
the analysis); nothing is fetched and nothing is written. The engine assesses
every crop exactly as the Report was assessed, and the result for the current
crop must equal the multi-year susceptibility written in the Report. When it
does not (the Report was stored before the method or its parameters changed),
the routes refuse to answer instead of showing numbers that contradict it.

The fixed example report and its stand-ins keep their placeholder answers.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.analyses import not_found, require_catalog_crop
from app.api.errors import ApiError, error_responses
from app.api.reports import require_report
from app.api.validation import ReportId
from app.catalog.crop_model import CatalogCrop
from app.catalog.crops import get_crop, list_crops
from app.contracts.report import Report
from app.contracts.simulation import (
    CompareResponse,
    CompareYear,
    CropSusceptibility,
    RankingResponse,
)
from app.contracts.source_data import SourceData
from app.engine.simulation import CropResult, Simulation, compare_years, simulate
from app.engine.simulation_texts import not_comparable_sentence, ranking_limitations
from app.mock import data
from app.mock import store as mock_store
from app.orchestrator import runtime
from app.orchestrator.params import LOG_ID_CHARS
from app.orchestrator.service import Orchestrator, utc_now
from app.storage.reports import ReportStore

router = APIRouter(prefix="/reports/{report_id}/simulation", tags=["simulation"])
logger = logging.getLogger("hydromiara.simulation")

Service = Annotated[Orchestrator, Depends(runtime.get_orchestrator)]


def _not_ready() -> ApiError:
    return ApiError(425, "report_not_ready", "Raport jest jeszcze przygotowywany.")


def _unknown_crop() -> ApiError:
    return ApiError(422, "unknown_crop", "Nieznana uprawa. Wybierz uprawę z listy.")


def _is_placeholder(report_id: str) -> bool:
    """True for the example report and its stand-ins, once they are ready."""
    if not mock_store.exists(report_id):
        return False
    if not mock_store.is_done(report_id):
        raise _not_ready()
    return True


def _mock_public(crop: CropSusceptibility) -> CropSusceptibility:
    return CropSusceptibility.model_validate(crop.model_dump(exclude={"deficit_in"}))


def _mock_ranking() -> RankingResponse:
    simulation = data.catalog().simulation
    others = sorted(simulation.others, key=lambda crop: crop.deficit_years)
    return RankingResponse(
        current=simulation.current,
        top=[_mock_public(crop) for crop in others[:3]],
        limitations=simulation.limitations,
    )


def _mock_compare(report_id: str, crop_id: str) -> CompareResponse:
    simulation = data.catalog().simulation
    other = next((crop for crop in simulation.others if crop.crop_id == crop_id), None)
    if other is None:
        raise _unknown_crop()
    years = [
        CompareYear(
            year=entry.year,
            current_deficit=entry.deficit,
            other_deficit=entry.year in other.deficit_in,
            partial=entry.partial,
        )
        for entry in data.report_for(report_id).multiyear_susceptibility.years
    ]
    return CompareResponse(current=simulation.current, other=_mock_public(other), years=years)


@dataclass(frozen=True)
class _Stored:
    """What the simulation reads from the store for one Report."""

    source_data: SourceData
    crop: CatalogCrop
    analysis_date: date
    report: Report


def _load(store: ReportStore, report_id: str) -> _Stored:
    now = utc_now()
    inputs = store.inputs(report_id, now)
    report_json = None if inputs is None else store.report_json(report_id, now)
    if inputs is None or report_json is None:
        # Unknown, deleted after the retention time, failed or still running.
        require_report(store.get(report_id, now))
        raise not_found()
    record = inputs.record
    require_catalog_crop(record.crop_id)
    return _Stored(
        source_data=inputs.source_data,
        crop=get_crop(record.crop_id),
        analysis_date=record.analysis_date,
        report=Report.model_validate_json(report_json),
    )


def _require_agreement(simulation: Simulation, report: Report) -> None:
    """Raise unless the current crop has a verdict equal to the one in the Report."""
    current = simulation.current
    if not current.assessed:
        raise ApiError(409, "simulation_not_available", not_comparable_sentence(current))
    verdict, reported = current.verdict, report.multiyear_susceptibility
    computed = (verdict.deficit_years, verdict.total_years, verdict.deficit_level)
    if computed != (reported.deficit_years, reported.total_years, reported.deficit_level):
        raise ApiError(
            409,
            "report_outdated",
            "Ten raport powstał przed zmianą sposobu liczenia, więc Symulacja pokazałaby inne "
            "liczby niż raport. Uruchom analizę ponownie, żeby porównać Uprawy.",
        )


def _public(result: CropResult) -> CropSusceptibility:
    verdict = result.verdict
    return CropSusceptibility(
        crop_id=result.crop.id,
        name=result.crop.name,
        deficit_years=verdict.deficit_years,
        total_years=verdict.total_years,
        deficit_level=verdict.deficit_level,
    )


def _ranking(store: ReportStore, report_id: str) -> RankingResponse:
    stored = _load(store, report_id)
    crops = list_crops()
    started = time.monotonic()
    simulation = simulate(stored.source_data, stored.crop, stored.analysis_date, crops)
    logger.info(
        "simulation %s ranking crops=%d duration_s=%.3f",
        report_id[:LOG_ID_CHARS], len(crops), time.monotonic() - started,
    )
    _require_agreement(simulation, stored.report)
    return RankingResponse(
        current=_public(simulation.current),
        top=[_public(result) for result in simulation.top],
        limitations=ranking_limitations(simulation),
    )


def _compare(store: ReportStore, report_id: str, crop_id: str) -> CompareResponse:
    stored = _load(store, report_id)
    chosen = next((crop for crop in list_crops() if crop.id == crop_id), None)
    if chosen is None:
        raise _unknown_crop()
    if chosen.id == stored.crop.id:
        raise ApiError(
            422,
            "same_crop",
            "Wybrana uprawa jest bieżącą Uprawą tego raportu. Wybierz inną uprawę do porównania.",
        )
    simulation = simulate(stored.source_data, stored.crop, stored.analysis_date, [chosen])
    _require_agreement(simulation, stored.report)
    other = simulation.other(chosen.id)
    if not other.assessed:
        raise ApiError(422, "crop_not_comparable", not_comparable_sentence(other))
    return CompareResponse(
        current=_public(simulation.current),
        other=_public(other),
        years=[
            CompareYear(
                year=year.year,
                current_deficit=year.current_deficit,
                other_deficit=year.other_deficit,
                partial=year.partial,
            )
            for year in compare_years(simulation.current, other)
        ],
    )


@router.get(
    "/ranking",
    response_model=RankingResponse,
    responses=error_responses(404, 409, 425),
    summary="Ranking upraw: trzy najmniej narażone na niedobór wody i bieżąca Uprawa",
)
async def ranking(report_id: ReportId, service: Service) -> RankingResponse:
    if _is_placeholder(report_id):
        return _mock_ranking()
    # Reading the store and running the balances block, so they run in a thread.
    return await asyncio.to_thread(_ranking, service.store, report_id)


@router.get(
    "/compare",
    response_model=CompareResponse,
    responses=error_responses(404, 409, 422, 425),
    summary="Porównanie bieżącej Uprawy z jedną wybraną, rok po roku",
)
async def compare(
    report_id: ReportId,
    crop_id: Annotated[str, Query(min_length=1, max_length=64)],
    service: Service,
) -> CompareResponse:
    if _is_placeholder(report_id):
        return _mock_compare(report_id, crop_id)
    return await asyncio.to_thread(_compare, service.store, report_id, crop_id)
