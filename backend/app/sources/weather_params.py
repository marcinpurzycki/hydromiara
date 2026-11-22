"""Parameters of the weather adapter, kept apart so they can change without code."""

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SOURCE_NAME = "Open-Meteo, archiwum pogodowe"
USER_AGENT = "hydro-analysis/0.1"

# Daily variables, in the order they are requested. Reference evapotranspiration
# is computed by the service with the FAO-56 Penman-Monteith method. Only what
# the water balance uses is requested: the archive counts a request against its
# free allowance by variables x days (cost = variables / 10 x days / 14), so the
# series of one analysis costs about 59 with two variables and 88 with three.
# The parameter `models` is not sent: the default series has no publication delay.
DAILY_VARIABLES = ("precipitation_sum", "et0_fao_evapotranspiration")

# Daily sums are aggregated over local days of the analysed country.
TIMEZONE = "Europe/Warsaw"

# The multi-year window is the 10 years directly preceding the analysis date;
# the series starts on 1 January of the year that is 10 years earlier.
MULTIYEAR_WINDOW_YEARS = 10

# PROVISIONAL: extra days before the window so that the soil water balance can
# settle before the first assessed year; the length has no scientific source yet.
BALANCE_WARMUP_DAYS = 120

# Engineering limit of one request: the full range is usually answered in well
# under a second, at times in up to 11 s.
TIMEOUT_S = 20.0

# Time one analysis gives the weather source (the limit set for it by the
# analysis run). A request refused for the rate limit is repeated only when the
# wait asked for by the archive and the repeated request fit into what is left.
FETCH_BUDGET_S = 12.0
# PROVISIONAL: engineering value without a measurement behind it; time kept for
# the repeated request itself (typical answers took 0.3-1.1 s).
RETRY_REQUEST_RESERVE_S = 3.0

# Status of an answer refused because the free allowance is used up.
RATE_LIMITED_STATUS = 429

# Headers of the archive that describe the free allowance; written to the log.
RATE_LIMIT_HEADERS = (
    "X-RateLimit-Cost",
    "X-RateLimit-Remaining",
    "X-RateLimit-Window",
    "Retry-After",
)

# What the user reads when there is no weather, by the reason code of the failure.
REASON_RATE_LIMITED = "rate_limited"
REASON_NO_ANSWER = "no_answer"
REASON_UNREADABLE = "unreadable"
FAILURE_MESSAGES = {
    REASON_RATE_LIMITED: (
        "Serwis pogodowy chwilowo odmówił odpowiedzi z powodu limitu zapytań. Bez danych "
        "pogodowych nie można ocenić sytuacji wodnej. Spróbuj ponownie za kilka minut."
    ),
    REASON_NO_ANSWER: "Archiwum pogodowe nie odpowiedziało lub nie ma danych dla tej daty.",
    REASON_UNREADABLE: "Archiwum pogodowe nie odpowiedziało lub nie ma danych dla tej daty.",
}
