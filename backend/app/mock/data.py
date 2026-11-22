"""Fixed placeholder payloads served until the real pipeline replaces them.

Values come from one trial calculation for a single parcel; examples and
simulation numbers are placeholders, not agronomic data. Crops are named by
their catalogue identifiers.
"""

import json
from functools import lru_cache
from pathlib import Path

from app.contracts.catalog import Example
from app.contracts.common import ContractModel
from app.contracts.parcels import ParcelDetail
from app.contracts.report import Limitation, Report
from app.contracts.simulation import CropSusceptibility

_DIR = Path(__file__).parent

MOCK_REPORT_ID = "demo"


class MockOtherCrop(CropSusceptibility):
    deficit_in: list[int]


class MockSimulation(ContractModel):
    current: CropSusceptibility
    others: list[MockOtherCrop]
    limitations: list[Limitation]


class MockCatalog(ContractModel):
    examples: list[Example]
    parcel: ParcelDetail
    simulation: MockSimulation


@lru_cache
def catalog() -> MockCatalog:
    raw = json.loads((_DIR / "catalog.json").read_text(encoding="utf-8"))
    return MockCatalog.model_validate(raw)


@lru_cache
def _report() -> Report:
    raw = json.loads((_DIR / "report.json").read_text(encoding="utf-8"))
    return Report.model_validate(raw)


def report_for(report_id: str) -> Report:
    """The fixed report under the requested identifier."""
    base = _report()
    meta = base.meta.model_copy(update={"report_id": report_id})
    return base.model_copy(update={"meta": meta})
