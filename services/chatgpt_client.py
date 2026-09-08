"""
Minimal ChatGPT client for the Brainstorm screen.

This is intentionally separate from services/ai_router.py (used by the
main AI screen) so Brainstorm's two-AI debate loop cannot interfere
with the existing AI Assistant conversation/session memory.
"""

from openai import OpenAI

from services.api_key_manager import APIKeyManager

DEFAULT_MODEL = "gpt-4o"


class ChatGPTClientError(Exception):
    pass


class ChatGPTClient:
    def __init__(self, model=DEFAULT_MODEL):
        self.model = model

    @staticmethod
    def has_key():
        return APIKeyManager.has_key()

    def send(self, system, messages):
        api_key = APIKeyManager.get_api_key()

        if not api_key:
            raise ChatGPTClientError(
                "OpenAI API key is not configured. "
                "Add it in Settings > Security Key Setup."
            )

        client = OpenAI(api_key=api_key)

        full_messages = [
            {"role": "system", "content": str(system or "")}
        ] + messages

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                max_tokens=1024,
            )
        except Exception as error:
            raise ChatGPTClientError(
                f"ChatGPT request failed: {type(error).__name__}: {error}"
            ) from error

        try:
            answer = response.choices[0].message.content.strip()
        except (AttributeError, IndexError) as error:
            raise ChatGPTClientError(
                f"ChatGPT returned an unexpected response: {error}"
            ) from error

        if not answer:
            raise ChatGPTClientError("ChatGPT returned an empty response.")

        return answer