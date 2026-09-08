"""
Minimal Claude (Anthropic) client for M12OS.

Uses `requests` directly instead of the `anthropic` package so no new
dependency is needed for the Buildozer/Android build -- `requests` is
already in requirements.txt.
"""

import json

import certifi
import requests

from services.claude_key_manager import ClaudeKeyManager

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 1024


class ClaudeClientError(Exception):
    pass


class ClaudeClient:
    """
    Thin wrapper around the Anthropic Messages API.

    Usage:
        client = ClaudeClient()
        answer = client.send(
            system="You are Claude, brainstorming with ChatGPT.",
            messages=[
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."},
            ],
        )
    """

    def __init__(self, model=DEFAULT_MODEL, max_tokens=DEFAULT_MAX_TOKENS):
        self.model = model
        self.max_tokens = max_tokens

    @staticmethod
    def has_key():
        return ClaudeKeyManager.has_key()

    def send(self, system, messages):
        api_key = ClaudeKeyManager.get_api_key()

        if not api_key:
            raise ClaudeClientError(
                "Claude API key is not configured. "
                "Add it in Settings > Security Key Setup."
            )

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": str(system or ""),
            "messages": messages,
        }

        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            response = requests.post(
                ANTHROPIC_API_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=60,
                verify=certifi.where(),
            )
        except requests.RequestException as error:
            raise ClaudeClientError(
                f"Claude request failed: {type(error).__name__}: {error}"
            ) from error

        if response.status_code != 200:
            raise ClaudeClientError(
                f"Claude API error {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as error:
            raise ClaudeClientError(
                f"Claude API returned invalid JSON: {error}"
            ) from error

        content_blocks = data.get("content", [])

        text_parts = [
            block.get("text", "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]

        answer = "".join(text_parts).strip()

        if not answer:
            raise ClaudeClientError("Claude returned an empty response.")

        return answer