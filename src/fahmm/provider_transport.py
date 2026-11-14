"""Optional, explicitly authorized OpenAI-compatible chat transport."""

from __future__ import annotations

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from fahmm.cloud_minutes import CloudRequestSnapshot
from fahmm.providers import provider_http_client


class ProviderError(RuntimeError):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def send_chat_completion(snapshot: CloudRequestSnapshot, api_key: str | None) -> str:
    """Return provider text; never expose raw SDK exceptions or request payloads."""
    try:
        with OpenAI(
            api_key=api_key or "fahmm-no-key",
            base_url=snapshot.profile.base_url,
            timeout=snapshot.profile.timeout_seconds,
            max_retries=0,
            http_client=provider_http_client(),
        ) as client:
            response = client.chat.completions.create(**snapshot.request_body)
        if not response.choices:
            raise ProviderError("format", "Provider returned no minutes; retry or choose another profile")
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("format", "Provider returned no usable minutes text")
        return content.strip()
    except APITimeoutError:
        raise ProviderError("timeout", "Provider timed out; retry or choose another profile") from None
    except RateLimitError:
        raise ProviderError("quota", "Provider rate limit or quota reached; retry later") from None
    except APIConnectionError:
        raise ProviderError("network", "Could not reach the provider; check the connection") from None
    except APIStatusError as exc:
        if exc.status_code in (402, 429):
            raise ProviderError("quota", "Provider quota or billing limit reached") from None
        raise ProviderError("provider", "Provider rejected the request; check the profile") from None
    except OpenAIError:
        raise ProviderError("format", "Provider response was not compatible; retry or change provider") from None
