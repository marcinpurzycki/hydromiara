"""The summary of a Report: the model's answer when it is usable, else the template.

`Summarizer.summarize` never raises because of the provider: a missing
configuration, a timeout, an error of the service, an unusable answer or an
answer that fails the check all end with the template and a reason code.
"""

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from app.contracts.report import Report, Summary, TraceEntry
from app.summary import params, prompt
from app.summary.check import answer_problem, clean_answer
from app.summary.config import provider_config
from app.summary.facts import summary_facts
from app.summary.provider import ChatProvider, ProviderError
from app.summary.template import template_summary

logger = logging.getLogger("hydromiara.summary")

RULE_ID = "summary.source"
_CONDITION = (
    "podsumowanie z modelu językowego tylko wtedy, gdy dostawca jest skonfigurowany, "
    "odpowiedział w limicie czasu i odpowiedź przeszła kontrolę; w każdym innym przypadku "
    "podsumowanie z szablonu"
)


@dataclass(frozen=True)
class SummaryOutcome:
    summary: Summary
    # Why the template was used; None when the model's answer was accepted.
    fallback_reason: str | None
    duration_s: float
    model: str | None = None


def template_outcome(
    report: Report, reason: str, duration_s: float = 0.0, model: str | None = None
) -> SummaryOutcome:
    return SummaryOutcome(template_summary(report), reason, duration_s, model)


def with_summary(report: Report, outcome: SummaryOutcome) -> Report:
    """The Report with this summary and with a trace entry about where it came from."""
    entry = TraceEntry(
        rule_id=RULE_ID,
        condition=_CONDITION,
        values={"fallback_reason": outcome.fallback_reason, "model": outcome.model},
        result=outcome.summary.source,
    )
    trace = [item for item in report.trace if item.rule_id != RULE_ID]
    return report.model_copy(update={"summary": outcome.summary, "trace": [*trace, entry]})


class Summarizer:
    def __init__(self, provider: ChatProvider | None = None) -> None:
        self._provider = provider

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "Summarizer":
        config = provider_config(env)
        if config is None:
            logger.info("summary provider not configured: summaries come from the template")
            return cls()
        logger.info(
            "summary provider configured model=%s timeout_s=%.1f", config.model, config.timeout_s
        )
        return cls(ChatProvider(config, transport=transport))

    @property
    def configured(self) -> bool:
        return self._provider is not None

    async def summarize(
        self, report: Report, *, time_left_s: float | None = None
    ) -> SummaryOutcome:
        """Summary of the Report within `time_left_s` (and the provider's own limit)."""
        provider = self._provider
        if provider is None:
            return template_outcome(report, "provider_not_configured")
        timeout_s = provider.config.timeout_s
        if time_left_s is not None:
            timeout_s = min(timeout_s, time_left_s)
        if timeout_s < params.MIN_CALL_TIME_S:
            return template_outcome(report, "no_time_left", model=provider.model)
        started = time.monotonic()
        try:
            facts = summary_facts(report)
            async with asyncio.timeout(timeout_s):
                raw = await provider.complete(
                    prompt.INSTRUCTION, prompt.user_message(facts), timeout_s
                )
            answer = clean_answer(raw)
            reason = answer_problem(answer, facts)
        except ProviderError as error:
            reason = error.code
        except TimeoutError:
            reason = "provider_timeout"
        except Exception as error:  # the analysis must not fail because of the summary
            # Only the kind of error: its text could quote the request.
            logger.warning("summary failed unexpectedly: %s", type(error).__name__)
            reason = "summary_error"
        duration_s = time.monotonic() - started
        if reason is not None:
            return template_outcome(report, reason, duration_s, provider.model)
        return SummaryOutcome(
            Summary(text=answer, source="llm"), None, duration_s, model=provider.model
        )
