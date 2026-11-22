"""The summary with a language model behind it: accepted answers, every way back to the template."""

import asyncio
import json
import logging

import httpx
import pytest

from app.contracts.report import Report
from app.summary import params, prompt
from app.summary.config import provider_config
from app.summary.provider import ProviderError
from app.summary.service import RULE_ID, Summarizer, with_summary
from tests.summary_helpers import KEY, MODEL, RecordedModel, cases, config, sent_data, summarizer
from tests.test_summary_check import GOOD

CASES = cases()
REPORT = CASES["deficit"]


def summarize(model: RecordedModel, report: Report = REPORT, **changes):
    time_left_s = changes.pop("time_left_s", None)
    return asyncio.run(summarizer(model, **changes).summarize(report, time_left_s=time_left_s))


def assert_template(outcome, reason: str) -> None:
    assert outcome.fallback_reason == reason
    assert outcome.summary == REPORT.summary and outcome.summary.source == "template"


def test_accepted_answer_becomes_the_summary():
    model = RecordedModel(f'  "{GOOD}"\n')
    outcome = summarize(model)
    assert outcome.summary.source == "llm" and outcome.summary.text == GOOD
    assert outcome.fallback_reason is None and outcome.model == MODEL
    report = with_summary(REPORT, outcome)
    assert Report.model_validate_json(report.model_dump_json()) == report
    entry = report.trace[-1]
    assert (entry.rule_id, entry.result) == (RULE_ID, "llm")
    assert entry.values == {"fallback_reason": None, "model": MODEL}
    # Nothing but the summary and the trace entry differs from the built Report.
    restored = report.model_copy(update={"summary": REPORT.summary, "trace": report.trace[:-1]})
    assert restored == REPORT


def test_request_follows_the_chat_completions_interface():
    model = RecordedModel(GOOD)
    summarize(model, base_url="https://llm.example.org/v1")
    (request,) = model.requests
    assert request.method == "POST"
    assert str(request.url) == "https://llm.example.org/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert set(body) == {"model", "messages", "max_completion_tokens"}
    assert body["model"] == MODEL
    assert body["max_completion_tokens"] == params.MAX_COMPLETION_TOKENS
    system, user = body["messages"]
    assert (system["role"], system["content"]) == ("system", prompt.INSTRUCTION)
    assert user["role"] == "user" and user["content"].startswith(prompt.DATA_START)
    # The optional field is sent only when the operator configured it.
    hinted = RecordedModel(GOOD)
    summarize(hinted, reasoning_effort="low")
    assert json.loads(hinted.requests[0].content)["reasoning_effort"] == "low"
    # The instruction holds no data of the Report; the data come apart from it.
    assert REPORT.headline not in system["content"] and REPORT.headline in user["content"]


@pytest.mark.parametrize("name", CASES)
def test_nothing_that_identifies_the_place_is_sent(name):
    report = CASES[name]
    model = RecordedModel()
    summarize(model, report)
    sent = model.requests[0].content.decode()
    parcel = report.meta.parcel
    for secret in (
        parcel.parcel_id, parcel.number, parcel.region, parcel.commune, parcel.county,
        parcel.voivodeship, report.meta.report_id, "coordinates", "geometry", "18.2", "52.75",
    ):
        assert secret not in sent, secret
    assert sent_data(model.requests[0])["naglowek"] == report.headline


def test_a_report_text_naming_the_place_is_left_out():
    parcel = REPORT.meta.parcel
    named = REPORT.model_copy(
        update={"headline": f"Działka {parcel.parcel_id}, obręb {parcel.region}: wody brakuje."}
    )
    with_point = REPORT.model_copy(update={"headline": "Punkt 52.75012, 18.20034: wody brakuje."})
    for report in (named, with_point):
        model = RecordedModel(GOOD)
        asyncio.run(summarizer(model).summarize(report))
        data = sent_data(model.requests[0])
        assert "naglowek" not in data and data["data_analizy"] == "20.06.2023"


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [(401, "provider_auth"), (403, "provider_auth"), (429, "provider_rate_limited"),
     (500, "provider_error"), (503, "provider_error"), (400, "provider_rejected"),
     (404, "provider_rejected")],
)
def test_error_status_falls_back_to_the_template(status_code, reason):
    model = RecordedModel(GOOD)
    model.status_code = status_code
    assert_template(summarize(model), reason)
    assert len(model.requests) == 1  # no retry


@pytest.mark.parametrize(
    ("raw_body", "reason"),
    [
        ("not json at all", "provider_bad_answer"),
        ("[]", "provider_bad_answer"),
        ('{"choices": []}', "provider_bad_answer"),
        ('{"choices": [{"message": {"content": 5}}]}', "provider_bad_answer"),
        ('{"choices": [{"message": {"content": null}}]}', "answer_empty"),
        ('{"choices": [{"message": {"content": "   "}}]}', "answer_empty"),
        ('{"choices": [{"message": {"content": null, "refusal": "no"}}]}', "provider_refused"),
        ('{"choices": [{"finish_reason": "length", "message": {"content": "Ala"}}]}',
         "answer_cut_off"),
        ('{"choices": [{"finish_reason": "content_filter", "message": {"content": ""}}]}',
         "provider_filtered"),
    ],
)
def test_unusable_answer_falls_back_to_the_template(raw_body, reason):
    model = RecordedModel()
    model.raw_body = raw_body
    assert_template(summarize(model), reason)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (GOOD + " Tak dalej." * 150, "answer_too_long"),
        (GOOD.replace("174 mm", "250 mm"), "number_not_in_report"),
        (GOOD + " Na Działce jest susza.", "drought_word"),
        (GOOD + " Ryzyko jest duże.", "avoided_word"),
        (GOOD + " Trzeba wykopać staw.", "term_not_in_report"),
    ],
)
def test_answer_that_fails_the_check_falls_back_to_the_template(answer, reason):
    assert_template(summarize(RecordedModel(answer)), reason)


def test_notation_differences_do_not_reject_an_answer():
    answer = (
        "Stan na 2023-06-20: Bieżąca sytuacja wodna to wyraźny niedobór. Wody brakowało w 9 z 10 "
        "lat. Kc wynosi 1.15, a opad pokrył 47 procent parowania. Jeśli masz możliwość "
        "nawadniania, jest ono teraz zasadne: 58–174 mm wody, czyli od 580 do 1 740 m3 na hektar."
    )
    outcome = summarize(RecordedModel(answer))
    assert outcome.fallback_reason is None and outcome.summary.text == answer


def test_time_limits_fall_back_to_the_template(monkeypatch):
    model = RecordedModel(GOOD)
    model.failure = httpx.ReadTimeout("slow")
    assert_template(summarize(model), "provider_timeout")
    model.failure = httpx.ConnectError("down")
    assert_template(summarize(model), "provider_unreachable")
    # Too little time left in the analysis: the provider is not even called.
    quiet = RecordedModel(GOOD)
    assert_template(summarize(quiet, time_left_s=params.MIN_CALL_TIME_S / 2), "no_time_left")
    assert quiet.requests == []
    # The time left in the analysis cuts a call the provider's own limit would allow.
    monkeypatch.setattr(params, "MIN_CALL_TIME_S", 0.01)
    slow = RecordedModel(GOOD)
    slow.delay_s = 5.0
    outcome = summarize(slow, time_left_s=0.05, timeout_s=30.0)
    assert_template(outcome, "provider_timeout")
    assert outcome.duration_s < 1.0


def test_unexpected_error_never_reaches_the_analysis():
    model = RecordedModel(GOOD)
    model.failure = RuntimeError(f"boom {KEY}")
    assert_template(summarize(model), "summary_error")


def test_without_configuration_the_template_is_used_and_nothing_is_called():
    for env in ({}, {params.API_KEY_ENV: KEY}, {params.MODEL_ENV: MODEL},
                {params.API_KEY_ENV: " ", params.MODEL_ENV: MODEL}):
        assert provider_config(env) is None
        service = Summarizer.from_env(env)
        assert not service.configured
        assert_template(asyncio.run(service.summarize(REPORT)), "provider_not_configured")


def test_configuration_is_read_from_the_environment():
    env = {params.API_KEY_ENV: KEY, params.MODEL_ENV: MODEL}
    assert provider_config(env) == config(
        base_url=params.DEFAULT_BASE_URL, timeout_s=params.DEFAULT_TIMEOUT_S
    )
    custom = provider_config(
        {**env, params.BASE_URL_ENV: "https://llm.example.org/v1/", params.TIMEOUT_ENV: "2,5"}
    )
    assert (custom.base_url, custom.timeout_s) == ("https://llm.example.org/v1", 2.5)
    unreadable = provider_config({**env, params.TIMEOUT_ENV: "soon"})
    assert unreadable.timeout_s == params.DEFAULT_TIMEOUT_S
    assert custom.reasoning_effort is None
    assert provider_config({**env, params.REASONING_EFFORT_ENV: "Low"}).reasoning_effort == "low"
    assert provider_config({**env, params.REASONING_EFFORT_ENV: "tiny"}).reasoning_effort is None
    assert provider_config({**env, params.BASE_URL_ENV: "http://127.0.0.1:8080/v1"}) is not None
    # The key is never sent to an address without TLS on another machine.
    assert provider_config({**env, params.BASE_URL_ENV: "http://llm.example.org/v1"}) is None
    assert provider_config({**env, params.BASE_URL_ENV: "llm.example.org"}) is None


def test_the_key_never_shows_up_outside_the_authorization_header(caplog):
    caplog.set_level(logging.DEBUG)
    env = {params.API_KEY_ENV: KEY, params.MODEL_ENV: MODEL}
    outcomes = []
    for prepare in (lambda m: None, lambda m: setattr(m, "status_code", 401),
                    lambda m: setattr(m, "failure", httpx.ConnectError(f"refused {KEY}")),
                    lambda m: setattr(m, "failure", RuntimeError(f"boom {KEY}"))):
        model = RecordedModel(GOOD)
        prepare(model)
        service = Summarizer.from_env(env, transport=model)
        outcomes.append(asyncio.run(service.summarize(REPORT)))
        assert model.requests[0].headers["authorization"] == f"Bearer {KEY}"
        assert KEY not in model.requests[0].content.decode()
    assert [outcome.summary.source for outcome in outcomes] == ["llm", *["template"] * 3]
    for outcome in outcomes:
        assert KEY not in repr(outcome)
        assert KEY not in with_summary(REPORT, outcome).model_dump_json()
    loaded = provider_config(env)
    assert KEY not in repr(loaded) and KEY not in str(loaded) and KEY not in f"{loaded}"
    assert KEY not in repr(ProviderError("provider_auth"))
    assert KEY not in caplog.text and "Bearer" not in caplog.text
    assert GOOD not in caplog.text and REPORT.headline not in caplog.text
    assert MODEL in caplog.text
