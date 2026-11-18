"""API backend with a mocked SDK client: no network."""
import base64
from types import SimpleNamespace

import anthropic
import pytest

from engine.backends import BackendError
from engine.backends.api import ApiBackend

SCHEMA = {"type": "object", "properties": {"total": {"type": "number"}}, "required": ["total"]}


class FakeClient:
    def __init__(self, resp=None, exc=None):
        self.messages = self
        self.resp, self.exc, self.calls = resp, exc, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.resp


def reply(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def test_schema_call_text_and_image():
    client = FakeClient(reply('{"total": 12.5}'))
    backend = ApiBackend("test-model", client=client)
    out = backend.generate("SYS", "<document>x</document>", schema=SCHEMA, image=(b"\x89PNGdata", "image/png"))
    assert out == '{"total": 12.5}'
    call = client.calls[0]
    assert call["model"] == "test-model" and call["system"] == "SYS"
    assert call["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    blocks = call["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png"
    assert base64.b64decode(blocks[0]["source"]["data"]) == b"\x89PNGdata"
    assert blocks[1] == {"type": "text", "text": "<document>x</document>"}


def test_plain_text_call_sends_no_output_config():
    client = FakeClient(reply("DRAFT - NOT SENT"))
    assert ApiBackend("m", client=client).generate("S", "u") == "DRAFT - NOT SENT"
    assert "output_config" not in client.calls[0]


def test_model_is_required():
    with pytest.raises(BackendError):
        ApiBackend("", client=FakeClient())


def test_api_error_becomes_backend_error():
    exc = anthropic.APIError("connection failed", request=None, body=None)
    with pytest.raises(BackendError, match="API error"):
        ApiBackend("m", client=FakeClient(exc=exc)).generate("S", "u", schema=SCHEMA)


def test_early_stop_and_empty_reply_fail_safe():
    with pytest.raises(BackendError, match="stopped early: refusal"):
        ApiBackend("m", client=FakeClient(reply("{}", stop="refusal"))).generate("S", "u", schema=SCHEMA)
    empty = SimpleNamespace(stop_reason="end_turn", content=[])
    with pytest.raises(BackendError, match="empty"):
        ApiBackend("m", client=FakeClient(empty)).generate("S", "u")
