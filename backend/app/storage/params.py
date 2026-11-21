"""Parameters of the report storage."""

from datetime import timedelta

# Environment variable with the path of the SQLite file, and the path used
# when it is not set (the reports volume of the container image).
DB_PATH_ENV = "REPORTS_DB_PATH"
DEFAULT_DB_PATH = "/data/reports/reports.sqlite3"

# PROVISIONAL: how long a Report (and a failed analysis) is kept before it is
# deleted. The project has not decided the retention time yet.
REPORT_RETENTION = timedelta(days=30)

# Engineering value: how often the running service deletes expired Reports.
PURGE_INTERVAL_S = 3600.0

# Engineering value: how long a statement waits for a locked database file.
BUSY_TIMEOUT_S = 5.0
