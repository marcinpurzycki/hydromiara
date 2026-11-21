"""Time limits and fixed answers of the analysis run.

All limits are engineering values, chosen so that an analysis ends within the
30 seconds the task allows; none of them decides a result.
"""

# Fetching all sources of one analysis may take this long in total.
ANALYSIS_BUDGET_S = 30.0

# Kept back from the budget for the engine and for writing the Report.
COMPUTE_RESERVE_S = 3.0

# Own limit of every source; a source that exceeds it is recorded as missing.
PARCEL_TIMEOUT_S = 8.0
WEATHER_TIMEOUT_S = 12.0

# Bytes of randomness in a report identifier (128 bits, URL-safe text).
REPORT_ID_BYTES = 16

# Characters of the report identifier written to the log. The identifier is
# the only key to a Report, so the log never holds it whole.
LOG_ID_CHARS = 6

# Time zone that decides what "today" is when the analysis date is checked.
LOCAL_TIMEZONE = "Europe/Warsaw"

SOURCE_NOT_CONNECTED_NOTE = "To źródło nie jest jeszcze używane w analizie."
SOURCE_TIMEOUT_NOTE = "Źródło nie odpowiedziało w wyznaczonym czasie ({seconds:.0f} s)."
SOURCE_ERROR_NOTE = "Źródło zgłosiło błąd."

# Code and Polish message of every way an analysis can fail.
FAILURES: dict[str, str] = {
    "parcel_unavailable": "Analiza nie powiodła się: nie udało się pobrać działki.",
    "weather_unavailable": (
        "Analiza nie powiodła się: brak danych pogodowych, bez których nie da się "
        "ocenić sytuacji wodnej."
    ),
    "analysis_timeout": (
        "Analiza nie powiodła się: źródła danych nie odpowiedziały w wyznaczonym czasie. "
        "Spróbuj ponownie."
    ),
    "analysis_interrupted": (
        "Analiza została przerwana przez ponowne uruchomienie usługi. Uruchom ją ponownie."
    ),
    "analysis_failed": "Analiza nie powiodła się z powodu błędu wewnętrznego. Spróbuj ponownie.",
}
