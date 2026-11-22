"""Client of the language model service (interface of the OpenAI Chat Completions API).

One request, no retries. Every failure is reported as a short code; neither the
key, the request nor the answer of the service is ever put into an error.
"""

import httpx

from app.summary import params
from app.summary.config import ProviderConfig


class ProviderError(Exception):
    """The service gave no usable answer; `code` says why, without any content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _status_code_reason(status_code: int) -> str:
    if status_code in (401, 403):
        return "provider_auth"
    if status_code == 429:
        return "provider_rate_limited"
    if status_code >= 500:
        return "provider_error"
    return "provider_rejected"


def answer_text(body: object) -> str:
    """The text of the first choice of a chat completion answer."""
    try:
        choice = body["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")
        refusal = message.get("refusal")
        content = message.get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ProviderError("provider_bad_answer") from None
    if refusal:
        raise ProviderError("provider_refused")
    if finish_reason == "length":
        raise ProviderError("answer_cut_off")
    if finish_reason == "content_filter":
        raise ProviderError("provider_filtered")
    if content is None or (isinstance(content, str) and not content.strip()):
        raise ProviderError("answer_empty")
    if not isinstance(content, str):
        raise ProviderError("provider_bad_answer")
    return content


class ChatProvider:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport

    @property
    def model(self) -> str:
        return self.config.model

    async def complete(self, instruction: str, data: str, timeout_s: float) -> str:
        """The model's answer to one instruction and one data message."""
        request = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": data},
            ],
            "max_completion_tokens": params.MAX_COMPLETION_TOKENS,
        }
        if self.config.reasoning_effort is not None:
            request["reasoning_effort"] = self.config.reasoning_effort
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "User-Agent": params.USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=timeout_s, headers=headers
            ) as client:
                response = await client.post(
                    self.config.base_url + params.COMPLETIONS_PATH, json=request
                )
        except httpx.TimeoutException:
            raise ProviderError("provider_timeout") from None
        except (httpx.HTTPError, httpx.InvalidURL):
            raise ProviderError("provider_unreachable") from None
        if response.status_code != 200:
            raise ProviderError(_status_code_reason(response.status_code))
        try:
            body = response.json()
        except ValueError:
            raise ProviderError("provider_bad_answer") from None
        return answer_text(body)
