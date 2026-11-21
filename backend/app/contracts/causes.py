"""Report parts: deficit causes, recommendations, irrigation."""

from typing import Literal

from pydantic import Field

from app.contracts.common import ContractModel, GeoJsonGeometry, NumberRange, Scalar

CauseId = Literal["precipitation", "soil", "runoff", "crop_demand"]

RecommendationGroup = Literal[
    "retencja krajobrazowa", "retencja glebowa", "agrotechnika", "nawadnianie"
]


class Indicator(ContractModel):
    name: str
    value: float | None
    unit: str
    threshold: float | None


class Fact(ContractModel):
    text: str
    source: str


class RetentionSite(ContractModel):
    id: str
    label: str
    geometry: GeoJsonGeometry


class Recommendation(ContractModel):
    id: str
    group: RecommendationGroup
    text: str
    gain: str = Field(description="Treść kolumny „Co uzyskasz”.")
    rule: str = Field(description="Reguła, która uruchomiła Rekomendację.")
    inputs: dict[str, Scalar] = Field(description="Wartości danych, które spełniły regułę.")
    citation: str
    retention_site: RetentionSite | None = None
    link: str | None = None


class Cause(ContractModel):
    id: CauseId
    found: bool
    finding: str
    indicator: Indicator
    facts: list[Fact]
    recommendations: list[Recommendation]


class Irrigation(ContractModel):
    applicable: bool = Field(description="False, gdy Data analizy jest poza Sezonem uprawy.")
    text: str
    justified: bool | None
    amount_mm: NumberRange | None
    amount_m3_ha: NumberRange | None
    timing: str | None
    reason_if_none: str | None
