"""Named parameters of the deficit causes and of the terrain analysis.

Everything that decides whether a cause is found is listed here, so replacing
a working value is a change of data, not of code. `CauseParams` carries the
same values as an object: callers pass a changed copy instead of editing the
module. None of the thresholds has a scientific source yet.
"""

from dataclasses import dataclass

# --- Thresholds of the four causes ------------------------------------------

# PROVISIONAL: no source; "too little precipitation against evaporation" is
# found when precipitation covers less than this share of the reference
# evapotranspiration ET0 of the same period, in percent.
PRECIPITATION_MIN_SHARE_OF_ET0_PCT: float = 50.0

# PROVISIONAL: no source; "the soil stores water poorly" is found when the
# available water capacity is below this many millimetres per metre of soil.
SOIL_MIN_AVAILABLE_WATER_MM_PER_M: float = 140.0

# PROVISIONAL: no source; "water runs off the field quickly" is found when the
# mean slope of the parcel is above this value, in percent.
RUNOFF_MAX_SLOPE_PCT: float = 2.0

# PROVISIONAL: no source for a threshold; "a crop with high water needs" is
# found when the mid-season crop coefficient Kc is above this value. Kc = 1 is
# the reference surface ET0 is defined for, so above it the crop at full cover
# uses more water than that surface.
CROP_DEMAND_MAX_KC_MID: float = 1.0

# --- Terrain analysis --------------------------------------------------------

# PROVISIONAL: no source; fewest grid cells inside the parcel outline from
# which a plane is fitted (three define a plane, the rest measure its misfit).
TERRAIN_MIN_CELLS: int = 6

# PROVISIONAL: no source; the cells must be spread across their narrower
# direction by at least this part of a cell (root mean square), otherwise they
# lie in one line and the slope across that line is unknown.
TERRAIN_MIN_CROSS_SPREAD_CELLS: float = 0.25

# PROVISIONAL: no source; the slope counts as told apart from the scatter of
# the elevations when it is at least this many times its standard error.
SLOPE_MIN_SIGNAL_TO_ERROR: float = 2.0

# PROVISIONAL: working value; share of the lowest cells whose mean position
# names the lowest part of the parcel. With this share the 1 m and the 30 m
# model pointed to places 3, 32 and 3 m apart on three measured parcels, while
# their single lowest points lay 17 to 90 m apart.
LOWEST_PART_SHARE: float = 0.1

# PROVISIONAL: no source; the lowest part is called central when the lowest
# cells lie closer to the middle of the analysed cells than this part of a cell.
LOWEST_PART_CENTRAL_WITHIN_CELLS: float = 0.5

# PROVISIONAL: no source; with fewer cells of the 30 m model inside the parcel
# the slope is reported as approximate.
COARSE_GRID_MIN_CELLS: int = 10

# The point heights are rounded to 0.1 m; below this slope, in percent, the
# report calls the downhill direction indicative.
ROUNDED_HEIGHTS_FLAT_SLOPE_PCT: float = 0.5


@dataclass(frozen=True)
class CauseParams:
    """The parameters above as one immutable object; defaults are the module values."""

    precipitation_min_share_of_et0_pct: float = PRECIPITATION_MIN_SHARE_OF_ET0_PCT
    soil_min_available_water_mm_per_m: float = SOIL_MIN_AVAILABLE_WATER_MM_PER_M
    runoff_max_slope_pct: float = RUNOFF_MAX_SLOPE_PCT
    crop_demand_max_kc_mid: float = CROP_DEMAND_MAX_KC_MID
    terrain_min_cells: int = TERRAIN_MIN_CELLS
    terrain_min_cross_spread_cells: float = TERRAIN_MIN_CROSS_SPREAD_CELLS
    slope_min_signal_to_error: float = SLOPE_MIN_SIGNAL_TO_ERROR
    lowest_part_share: float = LOWEST_PART_SHARE
    lowest_part_central_within_cells: float = LOWEST_PART_CENTRAL_WITHIN_CELLS
    coarse_grid_min_cells: int = COARSE_GRID_MIN_CELLS

    def __post_init__(self) -> None:
        thresholds = (
            self.precipitation_min_share_of_et0_pct,
            self.soil_min_available_water_mm_per_m,
            self.runoff_max_slope_pct,
            self.crop_demand_max_kc_mid,
        )
        if min(thresholds) <= 0:
            raise ValueError("cause thresholds must be positive")
        if self.terrain_min_cells < 4:
            raise ValueError("a plane with a misfit needs at least four cells")
        if self.terrain_min_cross_spread_cells <= 0 or self.slope_min_signal_to_error <= 0:
            raise ValueError("terrain analysis limits must be positive")
        if not 0 < self.lowest_part_share <= 1 or self.lowest_part_central_within_cells < 0:
            raise ValueError("the lowest part share must lie within 0-1")


DEFAULT_CAUSE_PARAMS = CauseParams()
