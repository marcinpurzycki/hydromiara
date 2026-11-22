"""Parameters of the terrain adapter, kept apart so they can change without code."""

USER_AGENT = "hydro-analysis/0.1"

# How far around the parcel the elevation grid reaches, so that slope can be
# computed up to the parcel boundary: one 30 m cell. Grids with this margin
# were compared between the sources when the point service was measured.
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
# Whole link, enforced by the chain: search plus read. Measured from the
# target server: at most 2.6 s inside an analysis.
COPERNICUS_LINK_TIMEOUT_S = 8.0

# --- GUGiK point height service (1 m terrain model) -------------------------
# Heights of listed points read from the national 1 m terrain model
# (airborne laser scanning). Described at the address below; the limits were
# measured on 21.11.2026, the service page states none.
GUGIK_SOURCE_NAME = "Numeryczny model terenu GUGiK w siatce 1 m, odczytany co 5 m"
GUGIK_URL = "https://services.gugik.gov.pl/nmt/"
GUGIK_REQUEST = "GetHByPointList"
# Coordinates go out in PL-1992; the service calls the northing `x` and the
# easting `y` (checked by measurement: swapped axes give a wrong height).
GUGIK_CRS = "EPSG:2180"
# Spacing of the point grid in metres; slope and aspect from it agree with the
# full 1 m model within 0.03 percentage points and 0.2 degrees (three parcels).
GUGIK_GRID_STEP_M = 5
# PROVISIONAL: most points asked for one parcel; larger parcels get a wider
# spacing. Only windows of up to about 4000 points were measured.
GUGIK_MAX_POINTS = 4000
# Points per GET request: the address is then about 8 kB; 900 points were
# refused with "414 Request-URI Too Long".
GUGIK_POINTS_PER_REQUEST = 400
# Beyond this many points in one request the service returns rows without a
# height and no error.
GUGIK_SERVICE_POINT_LIMIT = 1000
GUGIK_PARALLEL_REQUESTS = 8
# PROVISIONAL: the link succeeds when at least this share of the grid points
# inside the parcel has a height; no source.
GUGIK_MIN_SHARE_INSIDE = 0.9
# Fewer points inside the parcel do not define a plane.
GUGIK_MIN_POINTS_INSIDE = 3
# PROVISIONAL: whole link, enforced by the chain; the longest successful run
# from the target server took 5.0 s (3.5 s in a later measurement).
GUGIK_LINK_TIMEOUT_S = 8.0
# Engineering limit of one request, so that a repeated request still fits in
# the limit of the link.
GUGIK_REQUEST_TIMEOUT_S = 3.5
