"""Parameters of the terrain adapter, kept apart so they can change without code."""

USER_AGENT = "hydro-analysis/0.1"

# PROVISIONAL: how far around the parcel the elevation grid reaches, so that
# slope can be computed up to the parcel boundary; one 30 m cell is assumed,
# the distance has no source yet.
WINDOW_MARGIN_M = 30.0

# --- Copernicus DEM GLO-30 ---------------------------------------------------
# Tiles of one by one degree, stored as Cloud Optimized GeoTIFF in a public
# bucket (https://registry.opendata.aws/copernicus-dem/); the tile covering a
# point is looked up in the Earth Search catalogue.
COPERNICUS_SOURCE_NAME = "Copernicus DEM GLO-30"
COPERNICUS_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
COPERNICUS_COLLECTION = "cop-dem-glo-30"
COPERNICUS_ASSET = "data"
# Only files of this bucket are opened, whatever the catalogue answers.
COPERNICUS_BUCKET_PREFIX = "s3://copernicus-dem-30m/"
COPERNICUS_BUCKET_REGION = "eu-central-1"
# Nominal grid spacing of the product (the `gsd` of its catalogue entries).
# The grid is geographic: one arc second in latitude everywhere, and 1.5 arc
# seconds in longitude north of 50 degrees, so cells are not exactly square.
COPERNICUS_RESOLUTION_M = 30.0
# Years in which the elevations were measured (TanDEM-X mission), as given in
# the product description of the Copernicus Data Space Ecosystem.
COPERNICUS_DATA_DATE = "2011/2015"

# Engineering limits. The catalogue answers in about 0.6 s and the window is
# read in about a second; the limits leave room for a slow connection.
COPERNICUS_SEARCH_TIMEOUT_S = 8.0
COPERNICUS_READ_TIMEOUT_S = 10.0
# Whole link, enforced by the chain: search plus read.
COPERNICUS_LINK_TIMEOUT_S = 15.0
