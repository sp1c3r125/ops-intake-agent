"""Across all packs: `run.py --all` end to end with a mock backend, and fake-data hygiene (SPEC core rule 11)."""
import json
import re
from pathlib import Path

import pytest

import run
from engine import inputs, pipeline
from tests.helpers import PACKS, SequenceBackend, load_answers, make_cfg

PACK_NAMES = run.discover(PACKS)
EXPECTED = {   # pack: (items, auto, needs a person, skipped), as designed in the fake data
    "construction_tenders": (10, 6, 4, 0), "finance_invoices": (10, 6, 4, 0), "finance_receipts": (12, 7, 5, 0),
    "hotel_messages": (12, 6, 5, 1), "hotel_reviews": (15, 11, 4, 0), "logistics_pod": (10, 6, 4, 0),
    "logistics_shipments": (12, 5, 6, 1), "property_leases": (8, 6, 2, 0), "property_maintenance": (12, 7, 5, 0),
}


def test_all_nine_packs_are_present():
    assert PACK_NAMES == sorted(EXPECTED)


def test_all_runs_every_pack_and_writes_the_index(tmp_path, capsys):
    cfg = make_cfg()
    answers = []
    for name in PACK_NAMES:                                    # run.py processes packs, and items, in sorted order
        pack = pipeline.load_pack(PACKS / name)
        items = inputs.load_items(pack.input_kind, pack.dir, pack.input_glob, cfg.image_mode)
        by_id = load_answers(name)
        answers += [by_id[i.id] for i in items if not i.preset_reason]
    backend = SequenceBackend(answers)
    out_root = tmp_path / "outputs"
    assert run.main(["--all"], cfg=cfg, backend=backend, packs_dir=PACKS, out_root=out_root) == 0

    printed = capsys.readouterr().out
    assert "Claude calls for this run" in printed and printed.index("Claude calls") < printed.index("Running")
    index = (out_root / "index.html").read_text(encoding="utf-8")
    for name in PACK_NAMES:
        total, auto, human, skip = EXPECTED[name]
        summary = json.loads((out_root / name / "results.json").read_text(encoding="utf-8"))["summary"]
        assert (summary["total"], summary["auto"], summary["human"], summary["skip"]) == (total, auto, human, skip), name
        assert f'href="{name}/dashboard.html"' in index
        for f in ("report.xlsx", "dashboard.html", "results.json", "log.jsonl"):
            assert (out_root / name / f).exists(), (name, f)
    assert backend._n == len(answers)                          # every canned answer was used exactly once
    assert (out_root / "finance_receipts" / "expenses_export.csv").exists()


def test_every_pack_says_the_organisation_is_fictional():
    for name in PACK_NAMES:
        pack = pipeline.load_pack(PACKS / name)
        assert "fictional" in pack.org.casefold(), name


def fake_text_files():
    for path in sorted(PACKS.rglob("*")):
        if path.suffix == ".eml":
            yield path, inputs._load_email(path).text            # decoded: raw .eml lines are soft-wrapped
        elif path.is_file() and path.suffix in {".csv", ".json", ".md"}:
            yield path, path.read_text(encoding="utf-8", errors="replace")
        elif path.suffix == ".pdf":
            try:
                yield path, "\n".join(inputs.pdf_pages(path))
            except Exception:
                continue


def test_fake_data_uses_only_example_domains_and_fictional_phone_numbers():
    emails = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
    urls = re.compile(r"https?://([A-Za-z0-9.-]+)")
    phones = re.compile(r"(?<![\d.$])(?:\(0\d\)|0[2-9])[ -]?\d{4}[ -]?\d{4}(?!\d)")
    problems = []
    for path, text in fake_text_files():
        problems += [f"{path.name}: email domain {d}" for d in emails.findall(text) if not d.endswith(".example")]
        problems += [f"{path.name}: url host {h}" for h in urls.findall(text) if not h.endswith(".example")]
        for m in phones.finditer(text):
            if not re.fullmatch(r"03 5550 \d{4}", m.group(0)):
                problems.append(f"{path.name}: phone {m.group(0)!r}")
    assert problems == []


def test_phone_pattern_catches_a_bad_number():
    phones = re.compile(r"(?<![\d.$])(?:\(0\d\)|0[2-9])[ -]?\d{4}[ -]?\d{4}(?!\d)")
    assert phones.search("call 03 9123 4567 now") and phones.search("0412345678")
    assert not phones.search("invoice 2026-11-20 total $1,800.00") and not phones.search("KF-48201")


def test_the_generators_are_repeatable():
    """Running a generator again must not change a committed file. Checked by regenerating into the same place and
    comparing bytes, for the generators whose output does not depend on a font."""
    import subprocess
    import sys
    before = {p: p.read_bytes() for name in ("hotel_reviews", "property_maintenance", "construction_tenders")
              for p in (PACKS / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    for name in ("hotel_reviews", "property_maintenance", "construction_tenders"):
        subprocess.run([sys.executable, str(PACKS / name / "make_fake_data.py")], check=True, capture_output=True)
    after = {p: p.read_bytes() for p in before}
    assert before == after
