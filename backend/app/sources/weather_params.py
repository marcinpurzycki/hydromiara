"""Parameters of the weather adapter, kept apart so they can change without code."""

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SOURCE_NAME = "Open-Meteo, archiwum pogodowe"
USER_AGENT = "hydro-analysis/0.1"

# Daily variables, in the order they are requested. Reference evapotranspiration
# is computed by the service with the FAO-56 Penman-Monteith method.
DAILY_VARIABLES = ("precipitation_sum", "et0_fao_evapotranspiration", "temperature_2m_mean")

# Daily sums are aggregated over local days of the analysed country.
TIMEZONE = "Europe/Warsaw"

# The multi-year window is the 10 years directly preceding the analysis date;
# the series starts on 1 January of the year that is 10 years earlier.
MULTIYEAR_WINDOW_YEARS = 10

# PROVISIONAL: extra days before the window so that the soil water balance can
# settle before the first assessed year; the length has no scientific source yet.
BALANCE_WARMUP_DAYS = 120

# Engineering limit: the full range is answered in well under a second.
TIMEOUT_S = 20.0
