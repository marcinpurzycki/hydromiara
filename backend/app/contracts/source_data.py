"""SourceData: everything fetched for one analysis, stored with the Report.

Source adapters fill it, the engine only reads it. Every part except
`parcel` and `weather` may be missing and the engine has to cope with that.
"""

from datetime import date as Date
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.contracts.common import ContractModel, GeoJsonGeometry

SourceTopic = Literal[
    "parcel", "weather", "soil", "terrain", "hydro", "satellite", "drought_background"
]


class ParcelData(ContractModel):
    parcel_id: str
    number: str
    region: str
    commune: str
    county: str
    voivodeship: str
    geometry: GeoJsonGeometry
    area_ha: float = Field(gt=0)
    centroid_lon: float
    centroid_lat: float


class WeatherDay(ContractModel):
    date: Date
    precipitation_mm: float | None
    et0_mm: float | None = Field(description="FAO-56 reference evapotranspiration.")
    temperature_mean_c: float | None


class WeatherData(ContractModel):
    grid_lat: float
    grid_lon: float
    days: list[WeatherDay]


class SoilLayer(ContractModel):
    top_cm: float
    bottom_cm: float
    sand_pct: float | None
    silt_pct: float | None
    clay_pct: float | None
    organic_carbon_g_kg: float | None
    water_33kpa_vol_pct: float | None = Field(description="Volumetric water content at 33 kPa.")
    water_1500kpa_vol_pct: float | None = Field(
        description="Volumetric water content at 1500 kPa."
    )


class SoilData(ContractModel):
    layers: list[SoilLayer]


class TerrainData(ContractModel):
    """Elevation grid, row by row from north to south."""

    resolution_m: float = Field(gt=0)
    crs: str = Field(description="CRS of the grid, e.g. EPSG:4326.")
    transform: tuple[float, float, float, float, float, float] = Field(
        description="Affine transform (a, b, c, d, e, f) from grid to CRS coordinates."
    )
    elevations_m: list[list[float | None]]


class HydroObject(ContractModel):
    kind: str = Field(description="Type of water object, e.g. river, ditch, reservoir.")
    name: str | None
    geometry: GeoJsonGeometry


class HydroData(ContractModel):
    objects: list[HydroObject]


class SatelliteScene(ContractModel):
    date: Date
    clear_share_pct: float = Field(ge=0, le=100, description="Clear pixels over the parcel.")
    ndvi: float | None
    ndmi: float | None


class SatelliteData(ContractModel):
    scenes: list[SatelliteScene]


class CdiDekad(ContractModel):
    date: Date = Field(description="First day of the ten-day period.")
    cdi_class: int | None = Field(description="Combined Drought Indicator class.")


class DroughtBackground(ContractModel):
    dekads: list[CdiDekad]


class SourceOutcome(ContractModel):
    """How one data category was obtained: which chain link answered and when."""

    topic: SourceTopic
    source_name: str | None = Field(description="Name of the link that answered.")
    chain_step: int | None = Field(ge=1, description="1 = primary source; null = no data.")
    ok: bool
    duration_s: float = Field(ge=0)
    data_date: str | None = Field(description="Day or date range the data refers to.")
    fetched_at: datetime
    message: str | None = None


class SourceData(ContractModel):
    parcel: ParcelData
    weather: WeatherData
    soil: SoilData | None = None
    terrain: TerrainData | None = None
    hydro: HydroData | None = None
    satellite: SatelliteData | None = None
    drought_background: DroughtBackground | None = None
    outcomes: list[SourceOutcome] = Field(default_factory=list)
