"""Named parameters of the water balance and of the two verdicts.

Everything that decides a result is listed here, so replacing a working value
is a change of data, not of code. `EngineParams` carries the same values as an
object: callers (tests, coefficient overrides) pass a changed copy instead of
editing the module.

Method source: Allen R.G., Pereira L.S., Raes D., Smith M. (1998). Crop
evapotranspiration: guidelines for computing crop water requirements. FAO
Irrigation and Drainage Paper 56 (below: FAO-56), chapter 8 "ETc under soil
water stress conditions":
  eq. 80  ETc adj = Ks * Kc * ET0
  eq. 82  TAW = 1000 * (theta_FC - theta_WP) * Zr
  eq. 83  RAW = p * TAW
  eq. 84  Ks = (TAW - Dr) / ((1 - p) * TAW)   for Dr > RAW, otherwise Ks = 1
  eq. 85  Dr,i = Dr,i-1 - (P - RO)i - Ii - CRi + ETc,i + DPi
  eq. 86  0 <= Dr,i <= TAW
  eq. 88  DPi = (P - RO)i + Ii - ETc,i - Dr,i-1 >= 0
Simplifications of the balance (runoff RO, irrigation I and capillary rise CR
taken as zero; constant root depth; p not adjusted for ETc) are described in
`balance.py` and `root_zone.py`.
"""

from dataclasses import dataclass

from app.sources import soil_params

# --- Shared scale -----------------------------------------------------------

# Words of the four-step deficit scale, index = deficit level 0-3.
DEFICIT_LEVEL_LABELS: tuple[str, str, str, str] = (
    "w normie",
    "lekki niedobór",
    "wyraźny niedobór",
    "silny niedobór",
)

# --- Root zone --------------------------------------------------------------

# PROVISIONAL: the balance uses the soil down to 100 cm, which is as deep as
# the soil data reach; FAO-56 Table 22 gives deeper roots for some crops
# (winter wheat 1.5-1.8 m). One value shared with the soil adapter.
ROOT_ZONE_LIMIT_CM: float = soil_params.PROFILE_DEPTH_CM

# PROVISIONAL: which end of the tabulated range of maximum rooting depth is
# used before the limit above is applied: 0 = shallow end, 1 = deep end. The
# choice inside the range has no source.
ROOT_DEPTH_RANGE_END: int = 0

# PROVISIONAL: stand-in for the available water capacity when the parcel has no
# usable soil profile. No source for a typical arable soil of Poland yet; the
# value lies inside the range FAO-56 Table 19 gives for medium-textured soils
# (loam: theta_FC - theta_WP = 0.13-0.18 m3/m3). A result based on it is flagged.
FALLBACK_AVAILABLE_WATER_MM_PER_M: float = 150.0

# --- Daily balance ----------------------------------------------------------

# PROVISIONAL: root zone depletion on the day before the first day of the
# series, as a share of TAW (0 = field capacity). The series starts in early
# autumn, a warm-up period ahead of the first assessed year; the true state is
# unknown (FAO-56 eq. 87 needs a measured water content).
INITIAL_DEPLETION_SHARE: float = 0.0

# --- Current water status ---------------------------------------------------

# PROVISIONAL: lowest stress coefficient Ks (FAO-56 eq. 84) of levels 0, 1, 2;
# anything lower is level 3. Trial values without a source.
CURRENT_LEVEL_MIN_KS: tuple[float, float, float] = (1.0, 0.75, 0.4)

# PROVISIONAL: length of the "recent days" sums of precipitation and ET0 shown
# next to the current status; descriptive only, taken from the trial calculation.
RECENT_DAYS: int = 30

# --- Multi-year susceptibility ----------------------------------------------

# The multi-year window is 10 years (project definition, not a tuned value).
WINDOW_YEARS: int = 10

# PROVISIONAL: a year counts as a deficit year when the critical period has at
# least this many stress days (days ending with Dr > RAW). Trial value; known
# to be too sensitive (9 of 10 years on the trial parcel).
DEFICIT_YEAR_MIN_STRESS_DAYS: int = 10

# PROVISIONAL: lowest number of deficit years of levels 1, 2, 3 on the 10-year
# scale (0-2 normal, 3-4 slight, 5-7 marked, 8-10 severe). No source.
SUSCEPTIBILITY_LEVEL_MIN_YEARS: tuple[int, int, int] = (3, 5, 8)

# PROVISIONAL: first and last month of the yearly sums of precipitation and of
# the climatic water balance (P - ET0) reported with each year; descriptive
# only, taken from the trial calculation (April-July).
CLIMATIC_BALANCE_MONTHS: tuple[int, int] = (4, 7)


@dataclass(frozen=True)
class EngineParams:
    """The parameters above as one immutable object; defaults are the module values."""

    root_zone_limit_cm: float = ROOT_ZONE_LIMIT_CM
    root_depth_range_end: int = ROOT_DEPTH_RANGE_END
    fallback_available_water_mm_per_m: float = FALLBACK_AVAILABLE_WATER_MM_PER_M
    initial_depletion_share: float = INITIAL_DEPLETION_SHARE
    current_level_min_ks: tuple[float, float, float] = CURRENT_LEVEL_MIN_KS
    recent_days: int = RECENT_DAYS
    window_years: int = WINDOW_YEARS
    deficit_year_min_stress_days: int = DEFICIT_YEAR_MIN_STRESS_DAYS
    susceptibility_level_min_years: tuple[int, int, int] = SUSCEPTIBILITY_LEVEL_MIN_YEARS
    climatic_balance_months: tuple[int, int] = CLIMATIC_BALANCE_MONTHS
    # Overrides the catalogue crop coefficient of bare soil; None keeps it.
    bare_soil_kc: float | None = None

    def __post_init__(self) -> None:
        if self.root_zone_limit_cm <= 0 or self.fallback_available_water_mm_per_m <= 0:
            raise ValueError("root zone depth and fallback capacity must be positive")
        if self.root_depth_range_end not in (0, 1):
            raise ValueError("the root depth range end is 0 (shallow) or 1 (deep)")
        if not 0 <= self.initial_depletion_share <= 1:
            raise ValueError("the initial depletion share must lie between 0 and 1")
        ks = self.current_level_min_ks
        if not 1 >= ks[0] > ks[1] > ks[2] > 0:
            raise ValueError("Ks thresholds must fall from at most 1 towards 0")
        years = self.susceptibility_level_min_years
        if not 0 < years[0] < years[1] < years[2]:
            raise ValueError("deficit-year thresholds must rise")
        first_month, last_month = self.climatic_balance_months
        if not 1 <= first_month <= last_month <= 12:
            raise ValueError("climatic balance months must be an ordered pair within a year")
        if min(self.recent_days, self.window_years, self.deficit_year_min_stress_days) < 1:
            raise ValueError("day and year counts must be at least 1")


DEFAULT_PARAMS = EngineParams()
