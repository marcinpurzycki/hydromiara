"""Summary of the source timings: how often data arrived in time, and how fast.

For every phase and source the summary counts the calls, the calls that gave
data and the calls that gave data within the time limit, and describes the
times of the calls that gave data: minimum, median, 90th percentile, maximum.
Calls without data are left out of the times on purpose: most of them ended
at the time limit, so their times say nothing about the source's speed. A call
without data is not always a slow one (a source may answer at once that it
has nothing for the place); the `message` column of the measurements tells.

The 90th percentile is the nearest-rank one: the smallest measured value that
at least 90% of the values do not exceed. With few values it equals the
maximum, which is the honest reading of a small sample.
"""

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from analysis_tools.source_timing import ANALYSIS, ANALYSIS_TOTAL, FIRST, ISOLATED, REPEAT
from analysis_tools.tables import markdown_table, text

ALL_CALLS = "all"
CALL_KINDS = (ALL_CALLS, FIRST, REPEAT)
PHASES = (ISOLATED, ANALYSIS)
SUMMARY_COLUMNS = (
    "phase", "source", "call", "calls", "with_data", "within_limit", "within_limit_pct",
    "limit_s", "min_s", "median_s", "p90_s", "max_s",
)  # fmt: skip
MARKDOWN_HEADERS = (
    "Phase", "Source", "Calls", "With data", "Within limit", "Limit [s]",
    "Min [s]", "Median [s]", "p90 [s]", "Max [s]", "First call median [s]",
    "Repeat call median [s]",
)  # fmt: skip


@dataclass(frozen=True)
class Distribution:
    count: int
    minimum: float
    median: float
    p90: float
    maximum: float


def percentile(values: Sequence[float], share: float) -> float:
    """Nearest-rank percentile: `share` is between 0 and 1, `values` is not empty."""
    ordered = sorted(values)
    rank = max(1, math.ceil(share * len(ordered)))
    return ordered[rank - 1]


def distribution(values: Sequence[float]) -> Distribution | None:
    """Minimum, median, 90th percentile and maximum; None for no values."""
    if not values:
        return None
    return Distribution(
        count=len(values),
        minimum=min(values),
        median=statistics.median(values),
        p90=percentile(values, 0.9),
        maximum=max(values),
    )


def share_pct(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(100.0 * part / whole, 1)


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _summary(phase: str, source: str, call: str, rows: Sequence[Mapping[str, str]]) -> dict:
    with_data = [row for row in rows if row["ok"] == "true"]
    # Calls whose time is not known (analyses of a remote service) are not judged.
    judged = [row for row in rows if row["within_limit"]]
    in_time = [row for row in judged if row["within_limit"] == "true"]
    times = [t for t in (_number(row["duration_s"]) for row in with_data) if t is not None]
    limits = {row["limit_s"] for row in rows if row["limit_s"]}
    spread = distribution(times)
    return {
        "phase": phase,
        "source": source,
        "call": call,
        "calls": len(rows),
        "with_data": len(with_data),
        "within_limit": len(in_time) if judged else None,
        "within_limit_pct": share_pct(len(in_time), len(judged)),
        "limit_s": "/".join(sorted(limits)),
        "min_s": None if spread is None else spread.minimum,
        "median_s": None if spread is None else spread.median,
        "p90_s": None if spread is None else spread.p90,
        "max_s": None if spread is None else spread.maximum,
    }


def summarise(rows: Sequence[Mapping[str, str]]) -> list[dict]:
    """One summary per phase, source and kind of call, in the order they first appear."""
    summaries = []
    for phase in PHASES:
        of_phase = [row for row in rows if row["phase"] == phase]
        sources = list(dict.fromkeys(row["source"] for row in of_phase))
        # The whole analysis first, then its sources.
        sources.sort(key=lambda source: source != ANALYSIS_TOTAL)
        for source in sources:
            of_source = [row for row in of_phase if row["source"] == source]
            for call in CALL_KINDS:
                chosen = [row for row in of_source if call in (ALL_CALLS, row["call"])]
                if chosen:
                    summaries.append(_summary(phase, source, call, chosen))
    return summaries


def _seconds(value: object) -> str:
    return "" if value is None else f"{float(value):.2f}"


def markdown(summaries: Sequence[Mapping[str, object]]) -> str:
    """One line per phase and source; first and repeat calls as two median columns."""
    by_key = {(s["phase"], s["source"], s["call"]): s for s in summaries}
    lines = []
    for summary in summaries:
        if summary["call"] != ALL_CALLS:
            continue
        phase, source = summary["phase"], summary["source"]
        first = by_key.get((phase, source, FIRST), {})
        repeat = by_key.get((phase, source, REPEAT), {})
        in_time = "not measured"
        if summary["within_limit"] is not None:
            in_time = f"{summary['within_limit']} ({text(summary['within_limit_pct'])}%)"
        lines.append(
            (
                phase, source, summary["calls"], summary["with_data"], in_time,
                summary["limit_s"], _seconds(summary["min_s"]), _seconds(summary["median_s"]),
                _seconds(summary["p90_s"]), _seconds(summary["max_s"]),
                _seconds(first.get("median_s")), _seconds(repeat.get("median_s")),
            )  # fmt: skip
        )
    return markdown_table(MARKDOWN_HEADERS, lines)
