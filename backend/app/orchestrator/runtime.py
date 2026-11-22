"""Application lifetime of the orchestrator: one store and one orchestrator per process.

On start: open the database, close analyses a previous process left unfinished,
delete expired Reports and keep deleting them periodically. On stop: cancel
running analyses and record them as interrupted.
"""

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from app.orchestrator import params
from app.orchestrator.service import Orchestrator
from app.storage import params as storage_params
from app.storage.reports import ReportStore
from app.summary.service import Summarizer

logger = logging.getLogger("hydromiara.analysis")

_orchestrator: Orchestrator | None = None


def configure_logging() -> None:
    """Send the service's own log lines (source timings) to the standard error stream."""
    root = logging.getLogger("hydromiara")
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def database_path() -> str:
    return os.environ.get(storage_params.DB_PATH_ENV) or storage_params.DEFAULT_DB_PATH


def build_summarizer() -> Summarizer:
    """The summary step as configured in the environment; a seam for the tests."""
    return Summarizer.from_env()


def local_today() -> date:
    """Today's date where the analysed parcels are; an analysis date may not be later."""
    return datetime.now(ZoneInfo(params.LOCAL_TIMEZONE)).date()


def get_orchestrator() -> Orchestrator:
    """Dependency of the routes; available while the application is running."""
    if _orchestrator is None:
        raise RuntimeError("the application lifespan has not started")
    return _orchestrator


async def _purge_periodically(orchestrator: Orchestrator) -> None:
    while True:
        await asyncio.sleep(storage_params.PURGE_INTERVAL_S)
        try:
            deleted = await orchestrator.purge()
        except Exception:  # keep the loop alive; the next round tries again
            logger.exception("deleting expired reports failed")
        else:
            if deleted:
                logger.info("deleted %d expired reports", deleted)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _orchestrator
    configure_logging()
    # Blocking work (files, rasters, the engine, the database) runs in threads
    # of the default executor; its size is set here instead of left to chance.
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=params.WORKER_THREADS, thread_name_prefix="analysis")
    )
    orchestrator = Orchestrator(ReportStore(database_path()), summarizer=build_summarizer())
    interrupted = await orchestrator.recover()
    deleted = await orchestrator.purge()
    logger.info(
        "report store ready: %d interrupted analyses closed, %d expired reports deleted",
        interrupted, deleted,
    )
    purger = asyncio.create_task(_purge_periodically(orchestrator))
    _orchestrator = orchestrator
    try:
        yield
    finally:
        _orchestrator = None
        purger.cancel()
        await asyncio.gather(purger, return_exceptions=True)
        await orchestrator.shutdown()
        await orchestrator.recover()
