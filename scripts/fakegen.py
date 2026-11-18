"""Helpers for the packs' make_fake_data.py scripts. Fake data only: fictional names, .example domains and
phone numbers in the form 03 5550 xxxx.

Every generator is seeded, so running it again gives the same files.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

from PIL import ImageFont

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FIXTURES = REPO / "tests" / "fixtures"
DEMO_TODAY = date(2026, 11, 20)           # same as the engine default DEMO_TODAY
MELBOURNE = timezone(timedelta(hours=11))

_MONO = ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"]
_SANS = ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
_SANS_BOLD = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]


def font(size, kind="sans"):
    for name in {"mono": _MONO, "sans": _SANS, "bold": _SANS_BOLD}[kind]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def reset(folder, *patterns):
    """Make `folder` exist and delete the files this generator makes (so a rerun starts clean)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for pattern in patterns:
        for p in folder.glob(pattern):
            p.unlink()
    return folder


def write_csv(path, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_answers(pack, answers):
    """The canned model answers for the pack's end-to-end test: {item id: answer}. Used by tests only."""
    path = FIXTURES / pack / "answers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(answers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_eml(path, sender, to, subject, body, when, attachments=()):
    """A plain-text email with optional attachments [(filename, bytes, maintype, subtype)].
    The MIME boundary is seeded from the subject so reruns give identical bytes."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Date"] = format_datetime(when)
    msg["Message-ID"] = f"<{hashlib.md5(subject.encode()).hexdigest()[:16]}@mail.example>"
    msg.set_content(body)
    for filename, data, maintype, subtype in attachments:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    random.seed(int(hashlib.md5(subject.encode()).hexdigest()[:8], 16))
    Path(path).write_bytes(bytes(msg))


def at(day, hour=9, minute=0):
    """A timezone-aware Melbourne datetime for an email's Date header."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=MELBOURNE)


# --------------------------------------------------------------------------- Kestrel Freight (shared)
# Used by logistics_pod and logistics_shipments. consignment_no, consignee, suburb, dispatch, expected,
# packages, status. All fictional.
KESTREL = [
    ("KF-48201", "Bellbird Hardware", "Acacia Ridge", "2026-11-09", "2026-11-12", 4, "delivered"),
    ("KF-48202", "Tern Street Pharmacy", "Indooroopilly", "2026-11-09", "2026-11-12", 2, "delivered"),
    ("KF-48203", "Lyrebird Cafe Supplies", "Newstead", "2026-11-10", "2026-11-13", 6, "delivered"),
    ("KF-48204", "Quokka Pet Store", "Chermside", "2026-11-10", "2026-11-13", 3, "delivered"),
    ("KF-48205", "Heron Bay Marine", "Wynnum", "2026-11-11", "2026-11-16", 8, "delivered"),
    ("KF-48206", "Saltbush Garden Centre", "Mount Gravatt", "2026-11-11", "2026-11-16", 12, "delivered"),
    ("KF-48207", "Wattle Street Books", "West End", "2026-11-12", "2026-11-17", 5, "delivered"),
    ("KF-48208", "Brolga Electrical Wholesale", "Rocklea", "2026-11-12", "2026-11-17", 7, "delivered"),
    ("KF-48209", "Kingfisher Print Works", "Fortitude Valley", "2026-11-13", "2026-11-18", 3, "delivered"),
    ("KF-48210", "Plover Medical Supplies", "Herston", "2026-11-13", "2026-11-18", 9, "delivered"),
    ("KF-48211", "Coolibah Furniture", "Capalaba", "2026-11-16", "2026-11-23", 10, "in_transit"),
    ("KF-48212", "Ibis Office Fitouts", "Eagle Farm", "2026-11-16", "2026-11-19", 6, "delayed"),
    ("KF-48213", "Pelican Imports", "Pinkenba", "2026-11-17", "2026-11-24", 14, "customs_hold"),
    ("KF-48214", "Currawong Cycles", "Woolloongabba", "2026-11-17", "2026-11-24", 4, "in_transit"),
    ("KF-48215", "Magpie Toys", "Sunnybank", "2026-11-18", "2026-11-25", 11, "in_transit"),
    ("KF-48216", "Jabiru Aquarium Supplies", "Cannon Hill", "2026-11-18", "2026-11-25", 2, "awaiting_pickup"),
]


def write_kestrel_csv(path):
    write_csv(path, ["consignment_no", "consignee", "suburb", "dispatch_date", "expected_date", "packages",
                     "status"], KESTREL)
