"""Service health, crop list and examples."""

from typing import Literal

from fastapi import APIRouter

from app.contracts.catalog import Crop, Example
from app.contracts.common import ContractModel
from app.mock import data

router = APIRouter(tags=["catalog"])


class Health(ContractModel):
    status: Literal["ok"]


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")


@router.get("/crops", response_model=list[Crop], summary="Zamknięta lista Upraw")
def crops() -> list[Crop]:
    return data.catalog().crops


@router.get("/examples", response_model=list[Example], summary="Sześć Przykładów")
def examples() -> list[Example]:
    return data.catalog().examples
