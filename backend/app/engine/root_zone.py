"""Root zone of a crop on a parcel: how much water it holds and when stress starts.

FAO-56, chapter 8: total available water TAW = 1000 * (theta_FC - theta_WP) * Zr
(eq. 82), readily available water RAW = p * TAW (eq. 83), stress coefficient
Ks = (TAW - Dr) / ((1 - p) * TAW) once the depletion Dr exceeds RAW (eq. 84).

Assumptions of this module:
- The root depth Zr is constant over the year: the tabulated maximum rooting
  depth of the crop, limited to the depth the soil data reach.
- The field without a crop has no roots and no depletion fraction p. Its soil
  water store is followed over the whole profile depth and no stress
  coefficient is defined (Ks = 1).
- The capacity per metre of soil comes from the soil category of the parcel,
  from a category estimated from its texture, or is a flagged stand-in value
  (`soil_capacity`); it is the same at every depth of the root zone.
"""

from dataclasses import dataclass

from app.catalog.crop_model import CatalogCrop
from app.contracts.source_data import SoilData
from app.engine.params import DEFAULT_PARAMS, EngineParams
from app.engine.soil_capacity import CapacitySource, SoilCapacity, soil_capacity


@dataclass(frozen=True)
class RootZone:
    """Water-holding properties of the soil layer the balance is run for."""

    depth_cm: float
    # Total available water TAW, mm.
    taw_mm: float
    # Depletion fraction p of the crop; None for the field without a crop.
    depletion_fraction: float | None
    capacity_source: CapacitySource = "iung_category"
    # True when the crop roots deeper than the depth used here.
    limited_by_profile: bool = False
    # What the capacity per metre was derived from; None when given directly.
    soil: SoilCapacity | None = None

    def __post_init__(self) -> None:
        if self.depth_cm <= 0 or self.taw_mm <= 0:
            raise ValueError("root zone depth and total available water must be positive")
        p = self.depletion_fraction
        if p is not None and not 0 < p < 1:
            raise ValueError("the depletion fraction must lie between 0 and 1")

    @property
    def raw_mm(self) -> float | None:
        """Readily available water RAW (FAO-56 eq. 83); None without a crop."""
        if self.depletion_fraction is None:
            return None
        return self.depletion_fraction * self.taw_mm

    @property
    def available_water_mm_per_m(self) -> float:
        return self.taw_mm / self.depth_cm * 100.0

    def is_stressed(self, depletion_mm: float) -> bool:
        """True when the depletion exceeds the readily available water."""
        raw = self.raw_mm
        return raw is not None and depletion_mm > raw

    def stress_coefficient(self, depletion_mm: float) -> float:
        """Ks for the given root zone depletion (FAO-56 eq. 84), within 0-1."""
        if not self.is_stressed(depletion_mm):
            return 1.0
        ks = (self.taw_mm - depletion_mm) / (self.taw_mm - self.raw_mm)
        return min(1.0, max(0.0, ks))


def root_depth_cm(crop: CatalogCrop, params: EngineParams = DEFAULT_PARAMS) -> tuple[float, bool]:
    """(depth used by the balance in cm, whether the soil data limit it)."""
    limit = params.root_zone_limit_cm
    if crop.growth is None:
        return limit, False
    crop_depth = crop.growth.root_depth_m.value[params.root_depth_range_end] * 100.0
    return min(crop_depth, limit), crop_depth > limit


def root_zone(
    soil: SoilData | None, crop: CatalogCrop, params: EngineParams = DEFAULT_PARAMS
) -> RootZone:
    """Root zone of the crop on the given soil; soil may be missing."""
    depth, limited = root_depth_cm(crop, params)
    p = None if crop.growth is None else crop.growth.depletion_fraction.value
    capacity = soil_capacity(soil, params.fallback_available_water_mm_per_m)
    return RootZone(
        depth_cm=depth,
        taw_mm=capacity.mm_per_m * depth / 100.0,
        depletion_fraction=p,
        capacity_source=capacity.source,
        limited_by_profile=limited,
        soil=capacity,
    )
