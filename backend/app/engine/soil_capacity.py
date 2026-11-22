"""Water a metre of the parcel's soil can hold for plants. Pure: no network, no clock.

Three ways, the first that the soil data allow:

1. `iung_category`: the soil drought susceptibility category of the IUNG-PIB
   map. The categories I-IV group mineral soils by their plant-available
   water (https://susza.iung.pulawy.pl/kategorie/, after Ślusarczyk 1979:
   below 127.5, 127.5-169.9, 170-202.5 and above 202.5 mm). The capacity of
   a parcel is the mean of the category capacities weighted by the share of
   the sampled points.
2. `texture_estimate`: a category estimated from texture and organic carbon
   with the equations of Saxton and Rawls (2006, Soil Sci. Soc. Am. J. 70:
   1569-1578, eq. 1 and 2, as implemented in the USDA ARS code `saxpar.for`).
   The equations give a capacity on a lower scale than the categories, so the
   balance uses the capacity of the estimated category, not the equation value.
3. `fallback`: a stand-in value, when neither is available or the map marks
   the parcel as organic soil, which the model does not describe.

Water contents at 33 and 1500 kPa stored with older soil data are not used:
they do not tell sandy soils from loamy ones.
"""

from dataclasses import dataclass
from typing import Literal

from app.contracts.source_data import SoilData, SoilLayer

CapacitySource = Literal["iung_category", "texture_estimate", "fallback"]

# The balance and the profile capacity use the soil down to 100 cm: the
# category capacities below were chosen for a root zone of that depth, so a
# different depth needs them chosen again.
PROFILE_DEPTH_CM: float = 100.0

# PROVISIONAL: plant-available water per metre of soil for the categories
# I-IV; values chosen inside the intervals published by IUNG-PIB (the outer
# two intervals are open), without a source of their own. The threshold of a
# deficit year was calibrated with them.
CATEGORY_CAPACITY_MM_PER_M: dict[int, float] = {1: 110.0, 2: 149.0, 3: 186.0, 4: 220.0}
CATEGORY_LABELS: dict[int, str] = {1: "I", 2: "II", 3: "III", 4: "IV"}

# PROVISIONAL: no source; the map decides when at least this share of the
# sampled parcel points carries a category (or is marked as organic soil).
MIN_DECIDING_SHARE_PCT: float = 50.0
# Map value for organic soils and soils of organic origin.
ORGANIC_CODE: int = 5

# Organic matter from organic carbon: 1.724 = 1 / 0.58 (Siebielec et al. 2020,
# p. 27); carbon in g/kg, matter in % of mass.
ORGANIC_MATTER_PER_CARBON_G_KG: float = 0.1 / 0.58
# PROVISIONAL: organic matter is capped in the equations, because the global
# maps give implausibly high carbon in the subsoil of some mineral soils.
MAX_ORGANIC_MATTER_PCT: float = 3.5
# PROVISIONAL: lower bounds of the estimated categories II, III and IV in mm
# per metre from the equations: the bounds of the IUNG-PIB intervals times
# 0.67, the measured ratio of the two scales on a small sample of parcels.
ESTIMATED_CATEGORY_FROM_MM_PER_M: tuple[float, float, float] = (85.0, 113.0, 135.0)
# PROVISIONAL: the two sources describe the parcel differently when their
# categories are at least this far apart.
DIVERGENT_FROM_CATEGORIES: int = 2


@dataclass(frozen=True)
class SoilCapacity:
    """Capacity per metre of soil and what it was derived from."""

    source: CapacitySource
    mm_per_m: float
    # Category the capacity rests on: the most frequent one of the map, or the estimated one.
    category: int | None = None
    # (category, share of the sampled points in %) of the map, largest first.
    shares: tuple[tuple[int, float], ...] = ()
    # Category estimated from texture, whenever the texture allows it.
    estimated_category: int | None = None
    # True when the category map was read, whether or not it decided.
    map_read: bool = False
    # True when the map marks the parcel as organic soil.
    organic: bool = False

    @property
    def mixed(self) -> bool:
        return self.source == "iung_category" and len(self.shares) > 1

    @property
    def divergent(self) -> bool:
        """True when the map and the texture estimate are far apart."""
        if self.source != "iung_category" or None in (self.category, self.estimated_category):
            return False
        return abs(self.category - self.estimated_category) >= DIVERGENT_FROM_CATEGORIES


def layer_capacity_mm_per_m(sand_pct: float, clay_pct: float, organic_carbon_g_kg: float) -> float:
    """Field capacity minus wilting point of one layer (Saxton and Rawls 2006)."""
    s, c = sand_pct / 100.0, clay_pct / 100.0
    om = min(organic_carbon_g_kg * ORGANIC_MATTER_PER_CARBON_G_KG, MAX_ORGANIC_MATTER_PCT)
    wilting_t = (
        -0.024 * s + 0.487 * c + 0.006 * om + 0.005 * s * om - 0.013 * c * om
        + 0.068 * s * c + 0.031
    )  # fmt: skip
    wilting = wilting_t + (0.14 * wilting_t - 0.02)
    field_t = (
        -0.251 * s + 0.195 * c + 0.011 * om + 0.006 * s * om - 0.027 * c * om
        + 0.452 * s * c + 0.299
    )  # fmt: skip
    field = field_t + (1.283 * field_t**2 - 0.374 * field_t - 0.015)
    return max(0.0, (field - wilting) * 1000.0)


def _layer_part(layer: SoilLayer, profile_cm: float) -> tuple[float, float] | None:
    """(capacity per metre, thickness in cm) of the layer part inside the profile."""
    thickness = min(layer.bottom_cm, profile_cm) - layer.top_cm
    values = (layer.sand_pct, layer.clay_pct, layer.organic_carbon_g_kg)
    if thickness <= 0 or None in values:
        return None
    return layer_capacity_mm_per_m(*values), thickness


def profile_capacity_mm_per_m(
    soil: SoilData, profile_cm: float = PROFILE_DEPTH_CM
) -> float | None:
    """Thickness-weighted capacity of the profile from the equations.

    None unless texture and organic carbon cover the whole profile depth.
    """
    parts = [part for layer in soil.layers if (part := _layer_part(layer, profile_cm))]
    covered = sum(thickness for _, thickness in parts)
    if covered < profile_cm:
        return None
    return sum(capacity * thickness for capacity, thickness in parts) / covered


def estimated_category(soil: SoilData) -> int | None:
    """Category estimated from texture and organic carbon; None without a full profile."""
    capacity = profile_capacity_mm_per_m(soil)
    if capacity is None:
        return None
    return 1 + sum(capacity >= bound for bound in ESTIMATED_CATEGORY_FROM_MM_PER_M)


def _map_shares(soil: SoilData) -> tuple[tuple[int, float], ...]:
    found = [(item.category, item.share_pct) for item in soil.drought_categories or []]
    return tuple(sorted((item for item in found if item[1] > 0), key=lambda i: (-i[1], i[0])))


def _organic_share(soil: SoilData) -> float:
    return sum(a.share_pct for a in soil.unclassified_areas or [] if a.code == ORGANIC_CODE)


def category_map_decides(soil: SoilData) -> bool:
    """True when the category map alone settles the capacity of the parcel."""
    classified = sum(share for _, share in _map_shares(soil))
    return max(classified, _organic_share(soil)) >= MIN_DECIDING_SHARE_PCT


def soil_capacity(soil: SoilData | None, fallback_mm_per_m: float) -> SoilCapacity:
    """Capacity per metre of the parcel's soil; soil data may be missing."""
    if soil is None:
        return SoilCapacity(source="fallback", mm_per_m=fallback_mm_per_m)
    shares = _map_shares(soil)
    classified = sum(share for _, share in shares)
    estimate = estimated_category(soil)
    map_read = soil.drought_categories is not None
    if classified >= MIN_DECIDING_SHARE_PCT:
        weighted = sum(CATEGORY_CAPACITY_MM_PER_M[cat] * share for cat, share in shares)
        return SoilCapacity(
            source="iung_category",
            mm_per_m=weighted / classified,
            category=shares[0][0],
            shares=shares,
            estimated_category=estimate,
            map_read=True,
        )
    if _organic_share(soil) >= MIN_DECIDING_SHARE_PCT:
        return SoilCapacity(
            source="fallback", mm_per_m=fallback_mm_per_m, map_read=True, organic=True
        )
    if estimate is not None:
        return SoilCapacity(
            source="texture_estimate",
            mm_per_m=CATEGORY_CAPACITY_MM_PER_M[estimate],
            category=estimate,
            estimated_category=estimate,
            map_read=map_read,
        )
    return SoilCapacity(source="fallback", mm_per_m=fallback_mm_per_m, map_read=map_read)
