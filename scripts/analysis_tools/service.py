"""The service the tools talk to, and what identifies a run of a tool.

Two modes. By default the application runs inside the tool's own process with
the real data sources and a report database in a temporary directory that is
removed at the end; no running service is needed and the stored source data
(with the time of every source) can be read. With a base address the tool
talks to a running service over HTTP and measures it end to end; the time of
every source is then only in the log of that service.
"""

import contextlib
import logging
import os
import platform
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from analysis_tools import REPOSITORY_DIR
from app.storage.params import DB_PATH_ENV
from app.storage.reports import ReportStore

IN_PROCESS = "in_process"
HTTP = "http"
# The same general client name the source adapters send; no names, no addresses.
USER_AGENT = "hydro-analysis/0.1"
HTTP_TIMEOUT_S = 30.0
# Set these when the tool runs where they cannot be found out (a container).
CODE_VERSION_ENV = "CODE_VERSION"
HOST_ENV = "PROBE_HOST"
SERVICE_LOGGER = "hydromiara"


@dataclass(frozen=True)
class Service:
    """Client of the analysis routes; `store` only when the application runs here."""

    client: httpx.Client
    mode: str
    store: ReportStore | None = None


@contextlib.contextmanager
def open_service(base_url: str | None, *, quiet: bool = True) -> Iterator[Service]:
    """The running service at `base_url`, or the application started in this process."""
    if base_url:
        with httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=HTTP_TIMEOUT_S,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            yield Service(client=client, mode=HTTP)
        return
    from fastapi.testclient import TestClient

    previous = os.environ.get(DB_PATH_ENV)
    with tempfile.TemporaryDirectory(prefix="analysis-tools-") as directory:
        path = Path(directory) / "reports.sqlite3"
        os.environ[DB_PATH_ENV] = str(path)
        try:
            from app.api.limits import NO_LIMITS
            from app.main import app

            # The only client is this tool, which keeps its own pace towards
            # the data services; the request limits of the service do not apply.
            app.state.rate_limiter.configure(NO_LIMITS)
            with TestClient(app) as client:
                if quiet:
                    # The service logs every source of every analysis; the tool
                    # prints its own progress line instead.
                    logging.getLogger(SERVICE_LOGGER).setLevel(logging.WARNING)
                yield Service(client=client, mode=IN_PROCESS, store=ReportStore(path))
        finally:
            if previous is None:
                os.environ.pop(DB_PATH_ENV, None)
            else:
                os.environ[DB_PATH_ENV] = previous


def _git(*arguments: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(REPOSITORY_DIR), *arguments],
            capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def code_version() -> str:
    """Commit of the code that runs: from the environment, else from git, else unknown."""
    given = os.environ.get(CODE_VERSION_ENV, "").strip()
    if given:
        return given
    commit = _git("rev-parse", "--short", "HEAD")
    if not commit:
        return "unknown"
    return f"{commit}-dirty" if _git("status", "--porcelain") else commit


def host_name() -> str:
    """Where the tool ran; timings from different machines must not be mixed up."""
    return os.environ.get(HOST_ENV, "").strip() or platform.node() or "unknown"


@dataclass(frozen=True)
class RunInfo:
    """What makes the rows of one run traceable: code, place, mode, parameters."""

    tool: str
    started_at: datetime
    code_version: str
    host: str
    mode: str
    parameters: dict[str, str | int | float | bool | None]

    def as_dict(self) -> dict:
        return {
            "tool": self.tool,
            "started_at": timestamp(self.started_at),
            "code_version": self.code_version,
            "host": self.host,
            "mode": self.mode,
            "parameters": dict(self.parameters),
        }

    def lines(self) -> list[str]:
        """Sentences put above a table, so that a pasted table says where it came from."""
        parameters = ", ".join(f"{name} {value}" for name, value in self.parameters.items())
        return [
            f"Tool: {self.tool}; run started {timestamp(self.started_at)} (UTC); "
            f"code {self.code_version}; host {self.host}; mode {self.mode}.",
            f"Parameters: {parameters}.",
        ]


def new_run(tool: str, mode: str, parameters: dict) -> RunInfo:
    return RunInfo(
        tool=tool,
        started_at=datetime.now(UTC),
        code_version=code_version(),
        host=host_name(),
        mode=mode,
        parameters=parameters,
    )


def timestamp(moment: datetime | None) -> str:
    """UTC time to the second, the one form used in every output file."""
    return "" if moment is None else moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
