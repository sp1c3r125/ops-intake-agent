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


PACKS = Path(__file__).resolve().parents[1] / "packs"
FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT_DRAFT = "Thank you for getting in touch. [STAFF TO CONFIRM: details]\n\nKind regards"


class SequenceBackend:
    """Answers extract calls from a list, in order (the pipeline processes items in sorted order).
    Plain-text calls (drafts) get `draft_reply`. Records every call."""
    name = "mock"

    def __init__(self, answers, draft_reply=DEFAULT_DRAFT):
        self.answers, self.draft_reply, self.calls, self._n = list(answers), draft_reply, [], 0

    def generate(self, system, user_text, schema=None, image=None):
        self.calls.append({"system": system, "user": user_text, "schema": schema, "image": image})
        if schema is None:
            if isinstance(self.draft_reply, Exception):
                raise self.draft_reply
            return self.draft_reply
        if self._n >= len(self.answers):
            raise BackendError("mock: out of canned answers")
        answer = self.answers[self._n]
        self._n += 1
        return json.dumps(answer) if not isinstance(answer, str) else answer

    def extract_calls(self):
        return [c for c in self.calls if c["schema"] is not None]

    def draft_calls(self):
        return [c for c in self.calls if c["schema"] is None]


def load_answers(pack_name):
    return json.loads((FIXTURES / pack_name / "answers.json").read_text(encoding="utf-8"))


def run_real_pack(pack_name, tmp_path, draft_reply=DEFAULT_DRAFT, cfg=None, answers=None, image_mode="vision"):
    """End-to-end run of packs/<pack_name> with canned answers from tests/fixtures/<pack_name>/answers.json.
    Returns (summary, {item id: result}, backend, output folder)."""
    from engine import inputs, pipeline
    cfg = cfg or make_cfg(image_mode=image_mode)
    pack = pipeline.load_pack(PACKS / pack_name)
    items = inputs.load_items(pack.input_kind, pack.dir, pack.input_glob, cfg.image_mode)
    answers = answers or load_answers(pack_name)
    ordered = [answers[i.id] for i in items if not i.preset_reason]
    backend = SequenceBackend(ordered, draft_reply)
    summary = pipeline.run_pack(pack, items, backend, cfg, tmp_path)
    out = tmp_path / pack_name
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))["items"]
    return summary, {r["item"]: r for r in results}, backend, out


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
