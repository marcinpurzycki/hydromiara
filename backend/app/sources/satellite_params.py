"""Parameters of the satellite adapter, kept apart so they can change without code.

Values without a note come from the project's own measurement of the two
scene services (ten years of scenes over four parcels in four regions, read
from the target server) and from the literature named next to them.
"""

COLLECTION = "sentinel-2-l2a"
USER_AGENT = "hydro-analysis/0.1"

# Layers read from a scene. Red (B04) and near infrared (B08) lie on a 10 m
# grid and give NDVI; narrow near infrared (B8A), short-wave infrared (B11)
# and the scene classification lie on a 20 m grid and give NDMI. Each
# catalogue has its own file names for them (see satellite_providers.py).
ASSET_SCL = "scl"
ASSET_RED = "red"
ASSET_NIR = "nir"
ASSET_NIR_NARROW = "nir08"
ASSET_SWIR = "swir16"
REQUIRED_ASSETS = (ASSET_SCL, ASSET_RED, ASSET_NIR, ASSET_NIR_NARROW, ASSET_SWIR)

# --- Which scenes are looked for -------------------------------------------

# Current window: this many days before the analysis date, and the date
# itself. Measured for every day of April-September 2018-2022: a 30-day
# window had no clear scene on 0-3% of days (15 days: 8-10%).
CURRENT_WINDOW_DAYS = 30
# Bands are read for at most this many clear scenes of the current window,
# the newest ones.
CURRENT_SCENES = 6

# Earlier years: a window of this many days on each side of the same day of
# the year, for this many years back, with at most this many clear scenes a
# year, the ones nearest to that day.
HISTORY_HALF_WINDOW_DAYS = 15
HISTORY_YEARS = 5
HISTORY_SCENES_PER_YEAR = 2

# Bands are never read for more scenes than this in one call.
MAX_SCENES = CURRENT_SCENES + HISTORY_YEARS * HISTORY_SCENES_PER_YEAR  # 16

# --- Which pixels count -----------------------------------------------------

# Scene classification classes of the Sentinel-2 L2A product counted as
# clear: 4 = vegetation, 5 = not vegetated (bare soil).
CLEAR_SCL_CLASSES = (4, 5)

# Smallest share of clear pixels over the parcel for a scene to be used.
# Own choice backed by the measurement: scenes are either fully clear over a
# parcel (22-25% of days) or fully covered (65-70%); a lower threshold gains
# 2-4% of scenes and lets cloud edges in.
MIN_CLEAR_SHARE_PCT = 95.0

# Pixels closer to the parcel boundary than half a pixel are left out: 5 m on
# the 10 m grid (Vajsova et al. 2020, Remote Sens. 12:2195; Sen4CAP ATBD,
# parcels heterogeneity check), and by the same rule 10 m on the 20 m grid.
FINE_BUFFER_M = 5.0
COARSE_BUFFER_M = 10.0

# An index is computed from at least this many pixels, counted separately on
# each grid ("at least 8 full pixels inside a border", Vajsova et al. 2020).
MIN_PIXELS = 8

# reflectance = stored value * scale + offset. The offset depends on the
# catalogue and on the processing version of the scene (satellite_providers.py).
REFLECTANCE_SCALE = 0.0001

# Decimal places of the reported indices.
INDEX_DECIMALS = 4

# --- Engineering limits ------------------------------------------------------

# Whole adapter call; when it runs out, scenes read so far are returned.
# Measured worst case of the full path from the target server: about 3 s with
# the primary service and about 9 s with the secondary one.
TIME_BUDGET_S = 12.0

# One catalogue request, and how many pages of one window are followed.
SEARCH_TIMEOUT_S = 8.0
SEARCH_MAX_PAGES = 3

# The 20 m windows are read with this margin so that they cover every pixel
# of the 10 m window around the parcel.
COARSE_MARGIN_M = 20.0

# A read token is asked for again when it expires sooner than this.
TOKEN_MARGIN_S = 300.0

# GDAL settings for reading single windows of remote cloud-optimised files:
# no directory listing, bounded waiting. File addresses may end with a read
# token, so requests are not limited by file extension.
GDAL_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_CONNECTTIMEOUT": 10,
    "GDAL_HTTP_TIMEOUT": 20,
}
