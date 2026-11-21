"""Parameters of the satellite adapter, kept apart so they can change without code."""

from app.sources.raster import DEFAULT_INWARD_BUFFER_M

COLLECTION = "sentinel-2-l2a"
USER_AGENT = "hydro-analysis/0.1"

# Layers read from a scene: red and near infrared on a 10 m grid, short-wave
# infrared and the scene classification on a 20 m grid. Each catalogue has
# its own file names for them (see satellite_providers.py).
ASSET_RED = "red"
ASSET_NIR = "nir"
ASSET_SWIR = "swir16"
ASSET_SCL = "scl"
REQUIRED_ASSETS = (ASSET_SCL, ASSET_RED, ASSET_NIR, ASSET_SWIR)

# --- Which scenes are looked for -------------------------------------------

# PROVISIONAL: length of one search window ending on the analysis date (or on
# the same day of an earlier year); no source yet for the right length.
WINDOW_DAYS = 30

# PROVISIONAL: how many earlier years get the same window; no source yet.
PREVIOUS_YEARS = 3

# PROVISIONAL: clear scenes returned per window, newest first; no source yet.
SCENES_PER_WINDOW = 1

# --- Which pixels count -----------------------------------------------------

# PROVISIONAL: smallest share of clear pixels over the parcel for a scene to
# be used; no source yet.
MIN_CLEAR_SHARE_PCT = 80.0

# Scene classification classes of the Sentinel-2 L2A product: 4 = vegetation,
# 5 = not vegetated (bare soil).
# PROVISIONAL: which classes count as clear has no source yet.
CLEAR_SCL_CLASSES = (4, 5)

# Pixels closer to the parcel boundary than this are left out (see raster.py,
# where the value is marked as provisional).
INWARD_BUFFER_M = DEFAULT_INWARD_BUFFER_M

# reflectance = stored value * scale + offset. The offset depends on the
# catalogue and on the processing version of the scene (satellite_providers.py).
REFLECTANCE_SCALE = 0.0001

# Decimal places of the reported index means.
INDEX_DECIMALS = 4

# --- Engineering limits ------------------------------------------------------

# Whole adapter call; when it runs out, scenes finished so far are returned.
TIME_BUDGET_S = 15.0

# One catalogue request.
SEARCH_TIMEOUT_S = 8.0
SEARCH_PAGE_LIMIT = 100
SEARCH_MAX_PAGES = 3

# Raster reads running at the same time (each is one remote file).
READ_WORKERS = 12

# Acquisition days of one window whose classification is read at the same
# time, newest first; the next batch is read only when this one had too few
# clear scenes.
SCL_BATCH_SIZE = 3

# The 20 m windows are read with this margin so that they cover every pixel
# of the 10 m window whatever the alignment of the two grids.
COARSE_MARGIN_M = 20.0

# A read token is asked for again when it expires sooner than this.
TOKEN_MARGIN_S = 300.0

# GDAL settings for reading single windows of remote cloud-optimised files:
# no directory listing, bounded waiting. File addresses may end with a read
# token, so requests are not limited by file extension.
GDAL_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_CONNECTTIMEOUT": 5,
    "GDAL_HTTP_TIMEOUT": 10,
}
