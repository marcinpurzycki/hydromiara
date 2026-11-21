"""Water a soil profile can hold for plants. Pure: no network, no clock.

Available water of a layer is the difference between its volumetric water
content at 33 kPa (field capacity) and at 1500 kPa (wilting point), times the
layer thickness (FAO-56, chapter 8, eq. 82). To change the method, replace
`available_water_capacity`; nothing else depends on how it is computed.
"""

from typing import NamedTuple

from app.contracts.source_data import SoilData, SoilLayer
from app.sources import soil_params as params


class WaterCapacity(NamedTuple):
    """Plant-available water in the part of the profile that has data."""

    total_mm: float
    covered_cm: float
    profile_cm: float

    @property
    def mm_per_m(self) -> float:
        """Capacity per metre of soil, from the covered part only."""
        return self.total_mm / self.covered_cm * 100.0

    @property
    def complete(self) -> bool:
        return self.covered_cm >= self.profile_cm


def layer_available_water_mm(layer: SoilLayer, profile_cm: float) -> tuple[float, float] | None:
    """(water in mm, thickness in cm) of the layer part inside the profile.

    None when the layer lies below the profile, lacks one of the two water
    contents, or holds less water at 33 kPa than at 1500 kPa.
    """
    thickness_cm = min(layer.bottom_cm, profile_cm) - layer.top_cm
    field_capacity, wilting_point = layer.water_33kpa_vol_pct, layer.water_1500kpa_vol_pct
    if thickness_cm <= 0 or field_capacity is None or wilting_point is None:
        return None
    if field_capacity < wilting_point:
        return None
    # 1 % of volume over 1 cm of soil is 0.1 mm of water.
    return (field_capacity - wilting_point) * thickness_cm * 0.1, thickness_cm


def available_water_capacity(
    soil: SoilData, profile_cm: float = params.PROFILE_DEPTH_CM
) -> WaterCapacity | None:
    """Plant-available water from the surface down to `profile_cm`.

    Layers without usable water contents are left out and lower `covered_cm`;
    None when no layer is usable.
    """
    parts = [part for layer in soil.layers if (part := layer_available_water_mm(layer, profile_cm))]
    if not parts:
        return None
    return WaterCapacity(
        total_mm=sum(water for water, _ in parts),
        covered_cm=sum(thickness for _, thickness in parts),
        profile_cm=profile_cm,
    )
