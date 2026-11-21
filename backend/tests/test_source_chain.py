"""Substitute chain: order of links, going down, time limits, broken links, no data."""

import asyncio

import pytest

from app.sources.chain import (
    NO_TIME_LEFT,
    TIMED_OUT,
    UNEXPECTED,
    ChainTexts,
    LinkFailed,
    LinkReading,
    run_chain,
)


class FakeLink:
    def __init__(self, name, data=None, *, error=None, delay_s=0.0, timeout_s=1.0, note=None):
        self.name, self.timeout_s = name, timeout_s
        self._data, self._error, self._delay_s, self._note = data, error, delay_s, note
        self.requests = []

    async def read(self, request):
        self.requests.append(request)
        await asyncio.sleep(self._delay_s)
        if self._error is not None:
            raise self._error
        return LinkReading(data=self._data, data_date="2020", note=self._note)


def run(links, topic="terrain", **options):
    return asyncio.run(run_chain(topic, links, "request", **options))


def test_first_link_answers_and_the_rest_is_not_asked():
    primary, substitute = FakeLink("primary", {"grid": 1}), FakeLink("substitute", {"grid": 30})
    result = run([primary, substitute])
    assert result.data == {"grid": 1} and not result.stepped_down
    outcome = result.outcome
    assert (outcome.topic, outcome.ok, outcome.chain_step) == ("terrain", True, 1)
    assert (outcome.source_name, outcome.data_date, outcome.message) == ("primary", "2020", None)
    assert outcome.fetched_at.tzinfo is not None
    assert primary.requests == ["request"] and substitute.requests == []
    assert [attempt.result for attempt in result.attempts] == ["answered"]
    assert result.limitations == ()


def test_failed_primary_link_leads_to_the_substitute_with_a_limitation():
    primary = FakeLink("primary", error=LinkFailed("usługa nie odpowiedziała"))
    substitute = FakeLink("substitute", {"grid": 30}, note="Uwaga do odczytu.")
    result = run([primary, substitute])
    outcome = result.outcome
    assert result.data == {"grid": 30} and result.stepped_down
    assert (outcome.ok, outcome.chain_step, outcome.source_name) == (True, 2, "substitute")
    assert "primary: usługa nie odpowiedziała" in outcome.message
    assert "użyto zamiennika: substitute" in outcome.message
    assert outcome.message.endswith("Uwaga do odczytu.")
    assert [(a.step, a.name, a.result) for a in result.attempts] == [
        (1, "primary", "failed"), (2, "substitute", "answered"),
    ]
    (limitation,) = result.limitations
    assert (limitation.affects, limitation.permanent) == ("recommendations", False)
    assert "mniej dokładnego zamiennika (substitute)" in limitation.text
    assert "Miejsc zatrzymania wody" in limitation.text


def test_link_over_its_time_limit_is_skipped():
    slow = FakeLink("slow", {"grid": 1}, delay_s=1.0, timeout_s=0.02)
    substitute = FakeLink("substitute", {"grid": 30})
    result = run([slow, substitute])
    assert result.outcome.chain_step == 2 and TIMED_OUT in result.outcome.message
    assert result.attempts[0].result == "timed_out"
    assert 0.02 <= result.attempts[0].duration_s < 0.5
    assert result.outcome.duration_s >= result.attempts[0].duration_s
    assert len(result.limitations) == 1


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyError("x"), ValueError()])
def test_unexpected_exception_in_a_link_does_not_stop_the_chain(error):
    result = run([FakeLink("broken", error=error), FakeLink("substitute", {"grid": 30})])
    assert result.data == {"grid": 30} and result.outcome.chain_step == 2
    assert result.attempts[0].result == "raised" and result.attempts[0].reason == UNEXPECTED
    assert "boom" not in result.outcome.message


def test_link_returning_nothing_counts_as_failed():
    result = run([FakeLink("empty", None), FakeLink("substitute", {"grid": 30})])
    assert result.outcome.chain_step == 2 and result.attempts[0].result == "failed"


def test_all_links_failing_give_no_data_with_the_reasons_in_order():
    links = [
        FakeLink("primary", error=LinkFailed("powód pierwszy")),
        FakeLink("second", error=RuntimeError()),
        FakeLink("third", {"grid": 1}, delay_s=1.0, timeout_s=0.01),
    ]
    result = run(links, texts=ChainTexts(no_data="Nie udało się pobrać danych."))
    outcome = result.outcome
    assert result.data is None and not outcome.ok
    assert outcome.chain_step is None and outcome.source_name is None
    assert outcome.message.startswith("Nie udało się pobrać danych. primary: powód pierwszy.")
    assert outcome.message.index("primary") < outcome.message.index("second")
    assert outcome.message.index("second") < outcome.message.index("third")
    assert [attempt.step for attempt in result.attempts] == [1, 2, 3]
    assert [link.requests for link in links] == [["request"]] * 3
    assert result.limitations == () and not result.stepped_down


def test_chain_without_links_gives_no_data():
    result = run([])
    assert result.data is None and not result.outcome.ok and result.attempts == ()
    assert result.outcome.message


def test_third_link_is_step_three():
    links = [
        FakeLink("primary", error=LinkFailed("a")),
        FakeLink("second", error=LinkFailed("b")),
        FakeLink("third", {"grid": 90}),
    ]
    result = run(links)
    assert result.outcome.chain_step == 3 and len(result.limitations) == 1
    assert "primary: a; second: b" in result.outcome.message


def test_budget_of_the_whole_chain_cuts_a_link_and_skips_the_rest():
    slow = FakeLink("slow", {"grid": 1}, delay_s=1.0, timeout_s=5.0)
    late = FakeLink("late", {"grid": 30})
    result = run([slow, late], budget_s=0.03)
    assert result.data is None and late.requests == []
    assert [attempt.result for attempt in result.attempts] == ["timed_out", "skipped"]
    assert NO_TIME_LEFT in result.outcome.message
    assert result.outcome.duration_s < 0.5


def test_equivalent_services_create_no_limitation():
    links = [FakeLink("first service", error=LinkFailed("x")), FakeLink("second service", [1])]
    result = run(links, topic="satellite")
    assert result.outcome.chain_step == 2 and result.stepped_down
    assert result.limitations == ()


def test_outer_cancellation_is_not_swallowed():
    async def cancelled() -> None:
        task = asyncio.create_task(
            run_chain("terrain", [FakeLink("slow", {"grid": 1}, delay_s=5.0)], "request")
        )
        await asyncio.sleep(0.01)
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancelled())
