"""Access to the command line tools in `scripts/` for their tests.

The tools live outside the backend package; importing this module puts their
directory on the import path. `no_wait` is a pace without spacing or caps.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from analysis_tools.pacing import Pace  # noqa: E402
from analysis_tools.runner import AnalysisResult, run_analyses  # noqa: E402
from analysis_tools.service import IN_PROCESS, RunInfo, Service, new_run  # noqa: E402
from app.storage.reports import ReportStore  # noqa: E402

EXAMPLE_INPUT = SCRIPTS_DIR / "examples" / "input_format_example.csv"
HEADER = "parcel_id,crop_id,analysis_date,label,region\n"
KNOWN_ID = "040704_2.0020.34/2"
# Two analyses the recorded sources can answer: one parcel, two dates.
TWO_ROWS = (
    HEADER
    + f"{KNOWN_ID},winter_wheat,2023-06-20,first,Kujawy\n"
    + f"{KNOWN_ID},winter_wheat,2023-06-10,second,Kujawy\n"
)


def no_wait() -> Pace:
    return Pace(0.0, 0, 0)


def local_service(client, database: Path) -> Service:
    """The application of a test as the tools see it when it runs in their process."""
    return Service(client=client, mode=IN_PROCESS, store=ReportStore(database))


def test_run() -> RunInfo:
    return new_run("test", IN_PROCESS, {"spacing_s": 0})


test_run.__test__ = False


def analyse(service: Service, rows) -> list[AnalysisResult]:
    return list(run_analyses(service, rows, no_wait(), poll_s=0.01, announce=lambda _: None))
