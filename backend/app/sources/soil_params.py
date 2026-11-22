"""Parameters of the soil adapter, kept apart so they can change without code."""

USER_AGENT = "hydro-analysis/0.1"

# --- Link 1: map of soil drought susceptibility categories (IUNG-PIB) --------

# Public map service (GeoServer) behind the category map of the agricultural
# drought monitoring system; address and layer read from the map page
# https://susza.iung.pulawy.pl/mapa-kategorii/ and the service capabilities.
CATEGORY_URL = "https://sgeo.iung.pl/geoserver/ows"
CATEGORY_LAYER = "Susza:katgl_landuse2024"
CATEGORY_SOURCE_NAME = "IUNG-PIB, mapa kategorii podatności gleb na suszę"
# Half of the side of the 3 x 3 pixel window asked around a point, degrees.
CATEGORY_WINDOW_HALF_DEG = 0.00005
# Property of the answer that holds the value of the map cell.
CATEGORY_PROPERTY = "GRAY_INDEX"
# Legend of the layer style: 1-4 are the categories I-IV; every other value
# marks an area without a category (5 organic soils, 11 forest, 12 water,
# 13 built-up, 14 transport and wasteland, 19 and 99 unclassified, 0 and 255
# no data).
CATEGORY_VALUES = (1, 2, 3, 4)
# Recorded for a point for which the service returns no map cell at all.
CODE_OUTSIDE_MAP = 0

# PROVISIONAL: engineering constant; the parcel is sampled on a lattice of at
# most this many points inside its outline (one answer is one 5 m map cell).
MAX_SAMPLE_POINTS = 25
# The densest lattice tried over the bounding box of the outline, per side.
MAX_LATTICE_SIDE = 15
# Requests to the category map running at the same time.
CATEGORY_CONCURRENCY = 8
# Engineering limit of the whole link; one answer took 0.26-0.48 s and 25
# points 1.0-1.4 s when measured.
CATEGORY_TIMEOUT_S = 5.0

# --- Link 2: texture and organic carbon (ISRIC SoilGrids 2.0, WCS) -----------

# Each property has its own map file; the coverage is called
# <property>_<depth>_mean (https://docs.isric.org/globaldata/soilgrids/wcs.html).
TEXTURE_URL = "https://maps.isric.org/mapserv"
TEXTURE_SOURCE_NAME = "ISRIC SoilGrids 2.0"
# Field of a soil layer -> (property of the service, divisor). The maps hold
# integers: sand, silt and clay in g/kg, organic carbon in dg/kg; divided by
# 10 they give % of mass and g/kg (ISRIC, SoilGrids FAQ, table of properties).
TEXTURE_PROPERTIES = {
    "sand_pct": ("sand", 10.0),
    "silt_pct": ("silt", 10.0),
    "clay_pct": ("clay", 10.0),
    "organic_carbon_g_kg": ("soc", 10.0),
}
# Standard depth intervals down to the profile depth of the water balance:
# label of the service -> (top, bottom) in cm.
TEXTURE_DEPTHS = {
    "0-5cm": (0.0, 5.0),
    "5-15cm": (5.0, 15.0),
    "15-30cm": (15.0, 30.0),
    "30-60cm": (30.0, 60.0),
    "60-100cm": (60.0, 100.0),
}
# The maps are kept in the interrupted Goode homolosine projection; definition
# from the ISRIC FAQ ("How can I use the Homolosine projection?"). Subsetting
# in geographic coordinates makes the service resample the map, so the window
# is always asked in the map's own projection.
HOMOLOSINE_PROJ = "+proj=igh +datum=WGS84 +no_defs +towgs84=0,0,0"
HOMOLOSINE_URI = "http://www.opengis.net/def/crs/EPSG/0/152160"
# Half of the side of the window asked around the point, metres (5 x 5 cells
# of 250 m).
TEXTURE_WINDOW_HALF_M = 600.0
# Requests to the texture service running at the same time.
TEXTURE_CONCURRENCY = 12
# Engineering limit of the whole link; the 20 layers took 2.2-3.3 s when measured.
TEXTURE_TIMEOUT_S = 8.0
# Added to the limit of the first link in the chain, which also waits for the
# texture, so that the texture's own limit ends the wait.
CHAIN_GRACE_S = 0.5
# Limit of the whole chain when the caller gives none.
TIMEOUT_S = CATEGORY_TIMEOUT_S + TEXTURE_TIMEOUT_S
