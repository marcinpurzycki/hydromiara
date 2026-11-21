"""Substitute chain: primary source, less accurate substitute, no data.

A chain is an ordered list of links for one data category, the primary source
first. Each link is asked in turn within its own time limit; the first one
with data wins and its position is the chain step. A link that fails, is too
slow or raises anything unexpected is skipped and never stops the chain.

The result carries the data, the outcome record (which link answered, chain
step, duration, date of the data, message), one record per link asked and the
report limitation created by going down the chain.

A link is any object with `name`, `timeout_s` and
`async read(request) -> reading`, where the reading has `data`, `data_date`
and `note`. A link without data for the request raises `LinkFailed` with the
reason in Polish.
"""

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, Literal, Protocol, TypeVar

from app.contracts.report import Limitation
from app.contracts.source_data import SourceOutcome, SourceTopic
from app.engine.source_limitations import step_down_limitation

T = TypeVar("T")

TIMED_OUT = "źródło nie odpowiedziało w wyznaczonym czasie"
UNEXPECTED = "źródło nie dało odpowiedzi, którą można odczytać"
EMPTY = "źródło nie ma danych dla tego zapytania"
NO_TIME_LEFT = "zabrakło czasu, aby zapytać to źródło"

AttemptResult = Literal["answered", "failed", "timed_out", "raised", "skipped"]


class LinkFailed(Exception):
    """A link has no data for this request; the text says why, in Polish."""


class Reading(Protocol):
    """What a link returns: the data, the date they refer to, a shortcoming."""

    data: Any
    data_date: str | None
    note: str | None


@dataclass(frozen=True)
class LinkReading(Generic[T]):
    """Ready-made reading for links that do not define their own."""

    data: T
    data_date: str | None = None
    note: str | None = None


class ChainLink(Protocol):
    """One source of a data category."""

    name: str
    timeout_s: float

    async def read(self, request: Any) -> Reading:
        """Data for the request, or LinkFailed."""
        ...


@dataclass(frozen=True)
class ChainTexts:
    """Polish wording of the outcome message of one data category."""

    no_data: str = "Żadne źródło nie dało danych."
    # Placeholders: {failures} = links that gave nothing, {name} = link used.
    stepped_down: str = (
        "Źródło podstawowe nie dało danych ({failures}); użyto zamiennika: {name}."
    )


@dataclass(frozen=True)
class Attempt:
    """One link that was asked, or skipped for lack of time."""

    step: int
    name: str
    result: AttemptResult
    duration_s: float
    # Why the link gave nothing; None for the link that answered.
    reason: str | None = None

    @property
    def failure(self) -> str:
        return f"{self.name}: {self.reason}"


@dataclass(frozen=True)
class ChainResult(Generic[T]):
    data: T | None
    outcome: SourceOutcome
    attempts: tuple[Attempt, ...]
    # The limitation created by going down the chain; empty at the first link.
    limitations: tuple[Limitation, ...] = ()

    @property
    def stepped_down(self) -> bool:
        return (self.outcome.chain_step or 1) > 1


async def _ask(link: ChainLink, request: Any, step: int, limit_s: float) -> tuple[Attempt, Any]:
    started = time.monotonic()

    def attempt(result: AttemptResult, reason: str | None = None) -> Attempt:
        return Attempt(step, link.name, result, round(time.monotonic() - started, 3), reason)

    try:
        async with asyncio.timeout(limit_s):
            reading = await link.read(request)
    except TimeoutError:
        return attempt("timed_out", TIMED_OUT), None
    except LinkFailed as exc:
        return attempt("failed", str(exc) or EMPTY), None
    except Exception:  # a broken link must not stop the chain
        return attempt("raised", UNEXPECTED), None
    if reading is None or reading.data is None:
        return attempt("failed", EMPTY), None
    return attempt("answered"), reading


async def run_chain(
    topic: SourceTopic,
    links: Sequence[ChainLink],
    request: Any,
    *,
    texts: ChainTexts = ChainTexts(),
    budget_s: float | None = None,
) -> ChainResult:
    """Ask the links in order until one has data.

    `budget_s` limits the whole chain: a link gets what is left of it when
    that is less than its own limit, and links without time left are skipped.
    """
    started = time.monotonic()
    attempts: list[Attempt] = []
    for step, link in enumerate(links, start=1):
        limit_s = link.timeout_s
        if budget_s is not None:
            left = budget_s - (time.monotonic() - started)
            if left <= 0:
                attempts.append(Attempt(step, link.name, "skipped", 0.0, NO_TIME_LEFT))
                continue
            limit_s = min(limit_s, left)
        attempt, reading = await _ask(link, request, step, limit_s)
        attempts.append(attempt)
        if reading is None:
            continue
        notes = []
        if len(attempts) > 1:
            failures = "; ".join(earlier.failure for earlier in attempts[:-1])
            notes.append(texts.stepped_down.format(failures=failures, name=link.name))
        if reading.note:
            notes.append(reading.note)
        outcome = _outcome(
            topic, started, link.name, step, reading.data_date, " ".join(notes) or None
        )
        limitation = step_down_limitation(outcome)
        return ChainResult(
            data=reading.data,
            outcome=outcome,
            attempts=tuple(attempts),
            limitations=() if limitation is None else (limitation,),
        )

    message = " ".join([texts.no_data, *(f"{attempt.failure}." for attempt in attempts)])
    return ChainResult(
        data=None,
        outcome=_outcome(topic, started, None, None, None, message),
        attempts=tuple(attempts),
    )


def no_data(topic: SourceTopic, message: str, started: float | None = None) -> SourceOutcome:
    """Outcome of a chain that could not be asked at all, e.g. for a wrong request."""
    begun = time.monotonic() if started is None else started
    return _outcome(topic, begun, None, None, None, message)


def _outcome(
    topic: SourceTopic,
    started: float,
    source_name: str | None,
    chain_step: int | None,
    data_date: str | None,
    message: str | None,
) -> SourceOutcome:
    return SourceOutcome(
        topic=topic,
        source_name=source_name,
        chain_step=chain_step,
        ok=chain_step is not None,
        duration_s=round(time.monotonic() - started, 3),
        data_date=data_date,
        fetched_at=datetime.now(UTC),
        message=message,
    )
