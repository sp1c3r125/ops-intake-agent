"""Shared test helpers: a mock backend that returns canned answers. No network, no cost."""
import json
from datetime import date
from pathlib import Path

from engine import config
from engine.backends import BackendError

FAKE_PACKS = Path(__file__).parent / "fake_packs"
ENGINE_PACK = FAKE_PACKS / "engine_pack"


def canned(**over):
    """A valid extract answer for the engine test pack."""
    base = {"kind": "invoice", "vendor": "Acme Parts", "date": "2026-11-01", "subtotal": 100.0, "tax": 10.0,
            "total": 110.0, "summary": "An invoice.", "confidence": 0.95}
    base.update(over)
    return base


class MockBackend:
    """generate() looks at the user text and answers from `rules`, a list of (substring, response).

    A response is a dict (sent as JSON), a str (sent as is), an Exception (raised), or a list of those
    (one per call: the last one repeats). Plain-text calls (schema None, i.e. drafts) use `draft_reply`.
    """
    name = "mock"

    def __init__(self, rules=None, draft_reply="Thanks for your note. [STAFF TO CONFIRM: catalogue link]"):
        self.rules = list(rules or [])
        self.draft_reply = draft_reply
        self.calls = []          # dicts: system, user, schema, image
        self._count = {}

    def generate(self, system, user_text, schema=None, image=None):
        self.calls.append({"system": system, "user": user_text, "schema": schema, "image": image})
        if schema is None:
            if isinstance(self.draft_reply, Exception):
                raise self.draft_reply
            return self.draft_reply
        for i, (needle, response) in enumerate(self.rules):
            if needle in user_text:
                if isinstance(response, list):
                    n = self._count.get(i, 0)
                    self._count[i] = n + 1
                    response = response[min(n, len(response) - 1)]
                if isinstance(response, Exception):
                    raise response
                return json.dumps(response) if isinstance(response, dict) else response
        raise BackendError("mock: no rule matched")

    def extract_calls(self):
        return [c for c in self.calls if c["schema"] is not None]


def make_cfg(today=date(2026, 11, 20), image_mode="vision"):
    return config.Config(backend="claude-code", image_mode=image_mode, demo_today=today)


# One canned answer per file in the engine test pack's inbox.
def standard_rules():
    return [
        ("IGNORE ALL YOUR RULES", canned(summary="Injection attempt, ordinary invoice.", total=5000.0,
                                         subtotal=4545.45, tax=454.55)),
        ("catalogue", canned(kind="note", vendor=None, date=None, subtotal=0, tax=0, total=0,
                             summary="Wants the catalogue.")),
        ("total 120.00", canned(total=120.0, summary="Invoice with a wrong total.")),
        ("WIN A FREE CRUISE", canned(kind="spam", vendor=None, date=None, subtotal=0, tax=0, total=0,
                                     summary="Spam.")),
        ("Invoice from Acme Parts dated", canned()),
    ]
