"""Production backend: the Anthropic SDK with the JSON-schema output format."""
from __future__ import annotations

import base64

import anthropic

from . import BackendError

MAX_TOKENS = 8000  # headroom in case the model thinks before answering


class ApiBackend:
    name = "api"

    def __init__(self, model, api_key=None, client=None):
        if not model:
            raise BackendError("ANTHROPIC_MODEL is required for the api backend")
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key)

    def generate(self, system, user_text, schema=None, image=None):
        content = []
        if image is not None:
            data, mime = image
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": mime,
                                       "data": base64.b64encode(data).decode("ascii")}})
        content.append({"type": "text", "text": user_text})

        kwargs = {}
        if schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}

        try:
            resp = self.client.messages.create(model=self.model, max_tokens=MAX_TOKENS, system=system,
                                               messages=[{"role": "user", "content": content}], **kwargs)
        except anthropic.APIError as e:
            raise BackendError(f"API error: {e}") from e

        if resp.stop_reason != "end_turn":  # refusal, max_tokens, ...
            raise BackendError(f"stopped early: {resp.stop_reason}")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        if not text:
            raise BackendError("empty response")
        return text
