"""Time limits and fixed answers of the analysis run.

All limits are engineering values, chosen so that an analysis ends within the
30 seconds the task allows; none of them decides a result.
"""

# Fetching all sources of one analysis may take this long in total.
ANALYSIS_BUDGET_S = 30.0

# Kept back from the budget for the engine and for writing the Report.
COMPUTE_RESERVE_S = 3.0

# Kept back from the budget for storing the Report: the summary step, which may
# wait for a language model, has to end this long before the budget does.
SAVE_RESERVE_S = 1.0

# Own limit of every source; a source that exceeds it is recorded as missing.
PARCEL_TIMEOUT_S = 8.0
WEATHER_TIMEOUT_S = 12.0
# The soil service answered in 11-35 s when measured, so no limit inside the
# budget gets every answer. This one is given to the adapter and is as long as
# the budget allows after a parcel fetch of typical length; an analysis whose
# soil answer comes later uses the stand-in water capacity and says so.
SOIL_TIMEOUT_S = 24.0
# The adapters below end on their own (15 s for the satellite time budget)
# and then report what they have; these limits only stop one that does not.
# Terrain: two chain links asked one after the other, 8 s each (measured from
# the target server: at most 3.5 s and 2.6 s), plus the adapter grace.
TERRAIN_TIMEOUT_S = 17.0
SATELLITE_TIMEOUT_S = 17.0
# Waters: the adapter's chain ends on its own (the live read of the class
# files within 12 s, then a local copy when there is one); this limit only
# stops a chain that does not.
HYDRO_TIMEOUT_S = 17.0
# Local files, read in well under a second.
DROUGHT_BACKGROUND_TIMEOUT_S = 5.0
# Added to an adapter's own limit, so that the adapter's reason for having no
# data is recorded rather than the general one.
ADAPTER_GRACE_S = 1.0

# A source the analysis can do without never waits past the end of the fetch
# budget less this margin, whatever its own limit and however long the parcel
# took: the Report is then built without it instead of the analysis failing.
SOURCE_DEADLINE_MARGIN_S = 1.0

# Worker threads shared by the blocking work of all running analyses: reading
# the drought files and the terrain tile, the engine and the database (two or
# three at a time per analysis; a terrain read cut by its limit keeps a thread
# for up to 10 s more). Satellite reads use the adapter's own threads (12 per
# analysis). A fixed number, so that it does not follow the processor count.
WORKER_THREADS = 16

# Bytes of randomness in a report identifier (128 bits, URL-safe text).
REPORT_ID_BYTES = 16

# Characters of the report identifier written to the log. The identifier is
# the only key to a Report, so the log never holds it whole.
LOG_ID_CHARS = 6

# Time zone that decides what "today" is when the analysis date is checked.
LOCAL_TIMEZONE = "Europe/Warsaw"

SOURCE_NOT_CONNECTED_NOTE = "To źródło nie jest jeszcze używane w analizie."
SOURCE_TIMEOUT_NOTE = "Źródło nie odpowiedziało w wyznaczonym czasie ({seconds:.0f} s)."
SOURCE_ERROR_NOTE = "Źródło nie dało odpowiedzi, którą można odczytać."

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
