"""Helpers for the summary tests: Reports of typical cases and a recorded language model."""

import asyncio
import json
from datetime import date

import httpx

from app.catalog.crops import get_crop
from app.contracts.analyses import CropHistory
from app.contracts.report import Report
from app.contracts.source_data import CdiDekad, DroughtBackground, SourceData
from app.orchestrator.report_builder import ReportInputs, build_report
from app.summary import prompt
from app.summary.config import ProviderConfig
from app.summary.provider import ChatProvider
from app.summary.service import Summarizer
from tests.analysis_helpers import ANALYSIS_DATE, NOW, stored_source_data
from tests.engine_helpers import recorded_weather, weather_day
from tests.history_helpers import years
from tests.limitation_helpers import complete_source_data

KEY = "test-key-not-a-real-secret-0123456789"
MODEL = "test-model"
# Names as the parcel service gives them, so that leaving them out can be tested.
PLACE = {
    "parcel_id": "040704_2.0020.34/2",
    "number": "34/2",
    "region": "Krusza Podlotowa",
    "commune": "Inowrocław",
    "county": "inowrocławski",
    "voivodeship": "kujawsko-pomorskie",
}


def build(
    crop_id: str = "winter_wheat",
    day: date = ANALYSIS_DATE,
    source_data: SourceData | None = None,
    history: CropHistory | None = None,
) -> Report:
    data = complete_source_data() if source_data is None else source_data
    inputs = ReportInputs(
        report_id="report-identifier-1",
        created_at=NOW,
        source_data=data.model_copy(update={"parcel": data.parcel.model_copy(update=PLACE)}),
        crop=get_crop(crop_id),
        analysis_date=day,
        crop_history=history,
    )
    return build_report(inputs)


def _wet() -> SourceData:
    """Every day rainy and without evaporation: no verdict shows a deficit."""
    days = [weather_day(day.date, 20.0, 0.0) for day in recorded_weather()]
    return complete_source_data(days)


def _divergent() -> SourceData:
    background = DroughtBackground(dekads=[CdiDekad(date=date(2023, 6, 11), cdi_class=0)])
    return complete_source_data().model_copy(update={"drought_background": background})


def cases() -> dict[str, Report]:
    """One Report per situation the summary has to word differently."""
    return {
        "deficit": build(),
        "no_deficit": build(source_data=_wet()),
        "out_of_season": build(day=date(2023, 8, 31)),
        "dormant": build(day=date(2023, 11, 15)),
        "bare_field": build("bare_field", date(2023, 7, 15)),
        "no_soil": build(source_data=stored_source_data()),
        "divergent": build(source_data=_divergent()),
        "with_history": build(history=years(y2015="bare_field", y2016="bare_field")),
    }


def config(**changes) -> ProviderConfig:
    values = {"api_key": KEY, "model": MODEL, "timeout_s": 5.0, **changes}
    return ProviderConfig(**values)


def chat_body(text: str | None, finish_reason: str = "stop", refusal: str | None = None) -> dict:
    """An answer shaped like a chat completion object."""
    message = {"role": "assistant", "content": text, "refusal": refusal}
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": MODEL,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
    }


def sent_data(request: httpx.Request) -> dict:
    """The Report selection a request carried to the model."""
    content = json.loads(request.content)["messages"][1]["content"]
    start = content.index(prompt.DATA_START) + len(prompt.DATA_START)
    return json.loads(content[start : content.index(prompt.DATA_END)])


class RecordedModel(httpx.AsyncBaseTransport):
    """Stands in for the language model service; never touches the network."""

    def __init__(self, answer: str | None = None) -> None:
        self.requests: list[httpx.Request] = []
        # None: repeat the headline of the Report, which every check accepts.
        self.answer = answer
        self.status_code = 200
        self.raw_body: str | None = None
        self.delay_s = 0.0
        self.failure: Exception | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.failure is not None:
            raise self.failure
        if self.raw_body is not None:
            return httpx.Response(self.status_code, text=self.raw_body)
        if self.status_code != 200:
            error = {"error": {"message": "refused", "type": "error", "code": "x"}}
            return httpx.Response(self.status_code, json=error)
        answer = self.answer
        if answer is None:
            answer = f"{sent_data(request)['naglowek']} To podsumowanie powstało z danych Raportu."
        return httpx.Response(200, json=chat_body(answer))


def summarizer(model: RecordedModel, **changes) -> Summarizer:
    return Summarizer(ChatProvider(config(**changes), transport=model))
