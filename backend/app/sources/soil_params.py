"""Parameters of the soil adapter, kept apart so they can change without code."""

QUERY_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
SOURCE_NAME = "ISRIC SoilGrids 2.0"
USER_AGENT = "hydro-analysis/0.1"

# Field of a soil layer -> property name in the service. The service stores
# integers; each property comes with its own divisor (`unit_measure.d_factor`)
# that turns them into the conventional units used here: sand, silt and clay
# in % of mass, organic carbon in g/kg, water content at 33 and 1500 kPa in
# % of volume (ISRIC, SoilGrids FAQ, table of properties and units).
PROPERTIES = {
    "sand_pct": "sand",
    "silt_pct": "silt",
    "clay_pct": "clay",
    "organic_carbon_g_kg": "soc",
    "water_33kpa_vol_pct": "wv0033",
    "water_1500kpa_vol_pct": "wv1500",
}
WATER_FIELDS = ("water_33kpa_vol_pct", "water_1500kpa_vol_pct")

# PROVISIONAL: the soil profile used for the water balance reaches 100 cm, which
# is as deep as the requested standard layers go; crops may root deeper.
PROFILE_DEPTH_CM = 100.0

# Standard depth intervals of the service down to the profile depth.
DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm")

# Only the mean prediction is requested, not quantiles or uncertainty.
VALUE_STATISTIC = "mean"

# Engineering limit for the whole request. Answers measured from a development
# machine took 11-35 s, so part of the requests will end without soil data; the
# service is in beta, without uptime guarantee, and its fair use policy allows
# 5 calls per minute.
TIMEOUT_S = 20.0

# Permanent limitation attached to every soil profile that was obtained.
UNVERIFIED_CAPACITY_TEXT = (
    "Pojemność wodna gleby pochodzi z globalnego modelu SoilGrids (siatka 250 m) "
    "i nie została zweryfikowana pomiarem na Działce."
)
