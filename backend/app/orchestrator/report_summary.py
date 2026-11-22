"""The summary step of an analysis: after the Report is built, before it is stored.

A Report cannot change once stored, so its summary is settled here. The built
Report already carries the template summary. A language model is asked for
another wording only for a fresh analysis, only when a provider is configured
and only within the time the analysis has left. A Report derived from stored
data is not sent anywhere and keeps the template summary, so deriving stays
quick and repeatable.

Without a configured provider the Report is stored exactly as built, so it can
be computed again from its stored source data. When the provider was asked,
the trace says where the summary came from and why the template was kept.
"""

import logging

from app.contracts.report import Report
from app.summary.service import Summarizer, with_summary

logger = logging.getLogger("hydromiara.analysis")


async def summarised(
    report: Report, summarizer: Summarizer, time_left_s: float, tag: str
) -> Report:
    """The Report with its final summary; never fails because of the provider."""
    outcome = await summarizer.summarize(report, time_left_s=time_left_s)
    logger.info(
        "analysis %s summary source=%s fallback_reason=%s model=%s duration_s=%.3f",
        tag, outcome.summary.source, outcome.fallback_reason, outcome.model, outcome.duration_s,
    )
    return with_summary(report, outcome) if summarizer.configured else report
