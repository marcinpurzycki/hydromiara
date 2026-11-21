"""Building blocks shared by all contract models."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base for every contract model: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


# Deficit level on the shared four-step scale:
# 0 = w normie, 1 = lekki niedobór, 2 = wyraźny niedobór, 3 = silny niedobór.
DeficitLevel = Annotated[int, Field(ge=0, le=3)]

ConfidenceLevel = Literal["wysoka", "średnia", "niska"]

# Value allowed in open key-value blocks (details, values, inputs, trace).
Scalar = bool | int | float | str | None

# Inclusive [min, max] range.
NumberRange = tuple[float, float]


class Confidence(ContractModel):
    level: ConfidenceLevel
    why: str


class GeoJsonGeometry(ContractModel):
    """GeoJSON geometry in EPSG:4326 (longitude, latitude)."""

    type: Literal[
        "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"
    ]
    coordinates: list[Any]


class ErrorResponse(ContractModel):
    """Body of every error response."""

    code: str
    message: str = Field(description="Tekst po polsku, gotowy do wyświetlenia.")
