"""Provider configuration read from the environment. The key never leaves this object."""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.summary import params

logger = logging.getLogger("hydromiara.summary")


@dataclass(frozen=True)
class ProviderConfig:
    # Kept out of the text form of the object, so that it cannot reach a log
    # or an error message by accident.
    api_key: str = field(repr=False)
    model: str
    base_url: str = params.DEFAULT_BASE_URL
    timeout_s: float = params.DEFAULT_TIMEOUT_S
    reasoning_effort: str | None = None

    def __str__(self) -> str:
        return repr(self)


def _base_url(raw: str | None) -> str | None:
    """The address to call, or None when it would send the key without protection."""
    url = (raw or params.DEFAULT_BASE_URL).strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return url
    if parts.scheme == "http" and parts.hostname in params.PLAIN_HTTP_HOSTS:
        return url
    return None


def _timeout_s(raw: str | None) -> float:
    if not raw:
        return params.DEFAULT_TIMEOUT_S
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        value = 0.0
    if value <= 0:
        logger.warning("%s is not a positive number; using the default", params.TIMEOUT_ENV)
        return params.DEFAULT_TIMEOUT_S
    return value


def _reasoning_effort(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if not value:
        return None
    if value not in params.REASONING_EFFORTS:
        logger.warning("%s has an unknown value; it is not sent", params.REASONING_EFFORT_ENV)
        return None
    return value


def provider_config(env: Mapping[str, str] | None = None) -> ProviderConfig | None:
    """The configured provider; None when the summary comes from the template only."""
    env = os.environ if env is None else env
    api_key = (env.get(params.API_KEY_ENV) or "").strip()
    model = (env.get(params.MODEL_ENV) or "").strip()
    if not api_key or not model:
        return None
    base_url = _base_url(env.get(params.BASE_URL_ENV))
    if base_url is None:
        logger.warning(
            "%s must be an https address (http only for this machine); "
            "the summary provider is switched off", params.BASE_URL_ENV,
        )
        return None
    return ProviderConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_s=_timeout_s(env.get(params.TIMEOUT_ENV)),
        reasoning_effort=_reasoning_effort(env.get(params.REASONING_EFFORT_ENV)),
    )
