ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"

ANTHROPIC_MODEL = "claude-fable-5-1"

# If Fable's safety classifiers decline a request, the API re-runs it on
# Anthropic's recommended fallback model within the same call.
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"
ANTHROPIC_FALLBACKS = "default"


class AnthropicRefusal(Exception):
    """Claude (and its fallback model) declined the request."""


def raise_if_refused(data: dict) -> None:
    """Raise AnthropicRefusal if the response was declined.

    Check this before reading content: a refusal is an HTTP 200 whose content
    may be empty or partial.
    """
    if data.get("stop_reason") == "refusal":
        details = data.get("stop_details") or {}
        raise AnthropicRefusal(details.get("category") or "unspecified")
