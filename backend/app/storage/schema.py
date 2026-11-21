"""Database schema: one row per analysis, from the start to the stored Report.

`state` is `running` while sources are fetched, `finalizing` from the moment
the crop history is frozen until the Report is written, then `done` or
`failed`. The trigger makes a written Report and its source data unchangeable.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    report_id               TEXT PRIMARY KEY,
    state                   TEXT NOT NULL
        CHECK (state IN ('running', 'finalizing', 'done', 'failed')),
    parcel_id               TEXT NOT NULL,
    crop_id                 TEXT NOT NULL,
    analysis_date           TEXT NOT NULL,
    created_ts              REAL NOT NULL,
    finished_ts             REAL,
    error_code              TEXT,
    error_message           TEXT,
    sources_json            TEXT NOT NULL,
    crop_history_json       TEXT,
    source_data_json        TEXT,
    source_limitations_json TEXT,
    report_json             TEXT
);

CREATE INDEX IF NOT EXISTS analyses_created ON analyses (created_ts);

CREATE TRIGGER IF NOT EXISTS report_is_immutable
BEFORE UPDATE ON analyses
WHEN OLD.report_json IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'a stored report cannot be changed');
END;
"""

UNFINISHED_STATES = ("running", "finalizing")
