"""Parameters of the water adapter, kept apart so they can change without code."""

USER_AGENT = "hydro-analysis/0.1"

# --- BDOT10k (GUGiK), one nationwide GeoParquet file per object class --------
# Address announced by GUGiK on 16.04.2026:
# https://www.geoportal.gov.pl/aktualnosci/nowy-sposob-udostepniania-danych-bdot10k-w-geoportalu/
BDOT_URL = "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/GeoParquet/{name}.parquet"
BDOT_SOURCE_NAME = "BDOT10k, Główny Urząd Geodezji i Kartografii"
BDOT_LOCAL_SOURCE_NAME = "BDOT10k, Główny Urząd Geodezji i Kartografii (kopia lokalna)"

# Kinds of water objects as they are stored with the Report and shown on the map.
DITCH = "ditch"
CANAL = "canal"
WATERCOURSE = "watercourse"
WATER_BODY = "water_body"

# Object classes in the order they are read (regulation of 27.07.2021 on the
# topographic objects database, annex 3): class name and the kind it gives.
BDOT_CLASSES: tuple[tuple[str, str], ...] = (
    ("OT_SWRM_L", DITCH),  # drainage ditch, axis
    ("OT_SWRS_L", WATERCOURSE),  # river or stream, axis
    ("OT_SWKN_L", CANAL),  # canal, axis
    ("OT_PTWP_A", WATER_BODY),  # surface water, area
)
# Surface water whose type (column RODZAJ) starts with this text is the area of
# a river or canal, so it counts as a watercourse, not as a water body.
FLOWING_WATER_PREFIX = "woda płynąca"

# Columns of the files. Rows are grouped by county in row groups of 10 000.
COUNTY_COLUMN = "TERYT"  # county code, 4 characters
GEOMETRY_COLUMN = "GEOM"  # WKB, little-endian
NAME_COLUMN = "NAZWA"
TYPE_COLUMN = "RODZAJ"
# The file metadata name the system "ETRF2000-PL / CS92", i.e. EPSG:2180; the
# WKB holds easting first, then northing, in metres.
BDOT_CRS = "EPSG:2180"
REPORT_CRS = "EPSG:4326"
# Characters of a parcel identifier that are the county code.
COUNTY_CODE_LENGTH = 4

# PROVISIONAL: objects up to this distance from the parcel outline are kept;
# the distance has no source in the literature.
RADIUS_M = 500.0
# Engineering limit of the stored objects, nearest first, so that an unusual
# place cannot make the Report large.
MAX_OBJECTS = 200
# Decimal places of the stored coordinates (about 0.1 m).
COORDINATE_DECIMALS = 6

# PROVISIONAL: engineering limit of the live read of all four classes, read
# one after another (measured: about 8 s, 10.1 s at most).
LIVE_TIMEOUT_S = 12.0
# One HTTP range request: connecting and waiting for a piece of the answer.
REQUEST_CONNECT_TIMEOUT_S = 4.0
REQUEST_READ_TIMEOUT_S = 6.0

# --- Local copy of the same files --------------------------------------------
# Directory with <class>.parquet files; the link is left out when a file is
# missing. Filling and refreshing the directory is not done by the adapter.
LOCAL_DIR_ENV = "WATER_DATA_PATH"
DEFAULT_LOCAL_DIR = "/data/water"
LOCAL_TIMEOUT_S = 4.0

# Wording.
NO_DATA = "Nie udało się pobrać danych o ciekach, rowach i zbiornikach w otoczeniu Działki."
STEPPED_DOWN = (
    "Odczyt bieżących danych o wodach nie dał wyniku ({failures}); użyto zamiennika: {name}."
)
WRONG_PARCEL = "Nie można ustalić położenia Działki, więc nie wyszukano wód w jej otoczeniu."
READ_FAILED = "nie udało się odczytać plików z danymi o wodach"
READ_TOO_SLOW = "odczyt plików z danymi o wodach trwał zbyt długo"
LOCAL_COPY_NOTE = (
    "Dane o rowach i ciekach pochodzą z kopii pobranej {day}, a nie z dzisiejszego odczytu."
)
# What the data cannot show, named whenever they are used.
SCOPE_LIMITATIONS: tuple[str, ...] = (
    "Położenie rowów, cieków i zbiorników pochodzi z państwowej bazy topograficznej BDOT10k. "
    "Baza nie obejmuje drenów pod powierzchnią pola ani stanu technicznego rowów (drożność, "
    "zastawki, przepusty), a rowy przydrożne nie są w niej traktowane jako rowy melioracyjne. "
    "Dane mogą być starsze niż rok i nie pokazują, czy w rowie albo zbiorniku jest teraz woda.",
    "Wody wyszukano w powiecie, w którym leży Działka, do 500 m od jej granicy. Rów, ciek "
    "lub zbiornik położony tuż za granicą powiatu mógł zostać pominięty.",
)
