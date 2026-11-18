"""property_leases: checks, the renewal flag that is not a reason, reminder files, the no-text-layer path, end to end."""
from datetime import date

import pytest
from openpyxl import load_workbook

from engine import inputs, ocr, pipeline
from tests.helpers import PACKS, make_cfg, run_real_pack

PACK_DIR = PACKS / "property_leases"


@pytest.fixture(scope="module")
def pack():
    return pipeline.load_pack(PACK_DIR)


def good(**over):
    d = {"tenant_names": ["Isabel Crowe", "Tom Crowe"], "property_address": "Unit 3, 44 Starling Street, Footscray VIC 3011",
         "start_date": "2026-02-01", "end_date": "2027-06-30", "rent_amount": 520.0, "rent_frequency": "weekly",
         "bond_amount": 2080.0, "renewal_option": True, "notice_days": 60,
         "special_conditions": ["No pets without written consent"], "confidence": 0.95}
    d.update(over)
    return d


def check(pack, data, today=date(2026, 11, 20)):
    return pack.checks("lease.pdf", {**data, "_meta": {}}, {"_today": today})


@pytest.mark.parametrize("over, expected", [
    ({}, []),
    ({"start_date": "2026-09-01", "end_date": "2025-08-31"}, ["bad_term"]),            # the typo case
    ({"start_date": "2026-09-01", "end_date": "2026-09-01"}, ["bad_term"]),            # not after the start
    ({"end_date": None}, ["bad_term"]),
    ({"start_date": "1 Feb 2026"}, ["bad_term"]),
    ({"rent_amount": None}, ["no_rent"]),
    ({"rent_amount": 0}, ["no_rent"]),
    ({"notice_days": None}, ["missing_notice"]),
    ({"end_date": "2027-02-18"}, ["renewal_due"]),                                       # 90 days: inside the window
    ({"end_date": "2027-02-19"}, []),                                                    # 91 days: outside
    ({"end_date": "2026-11-20"}, ["renewal_due"]),                                       # ends today
    ({"end_date": "2026-11-19", "start_date": "2026-01-01"}, []),                       # already ended: not "due"
    ({"notice_days": None, "rent_amount": None, "start_date": "2027-01-01", "end_date": "2026-01-01"},
     ["bad_term", "no_rent", "missing_notice"]),
])
def test_each_check_fires(pack, over, expected):
    assert check(pack, good(**over)) == expected


def test_demo_today_drives_the_renewal_window(pack):
    assert check(pack, good(end_date="2027-06-30"), today=date(2027, 4, 15)) == ["renewal_due"]
    assert check(pack, good(end_date="2027-06-30"), today=date(2026, 11, 20)) == []


def test_renewal_due_alone_does_not_send_a_lease_to_a_person(pack):
    assert pack.route(good(), ["renewal_due"]) == "auto"
    assert pack.route(good(), []) == "auto"
    assert pack.route(good(), ["renewal_due", "missing_notice"]) == "human"
    assert pack.route(good(), ["bad_term"]) == "human"


def meta(*reasons):
    return {"_meta": {"reasons": list(reasons), "route": "auto"}}


@pytest.mark.parametrize("end, notice, decide_by", [
    ("2027-01-31", 60, "2026-12-02"),
    ("2027-06-14", 90, "2027-03-16"),            # a long notice period is used as it is
    ("2027-02-28", 30, "2026-12-30"),            # a short one is raised to 60 days
    ("2027-02-28", 60, "2026-12-30"),
])
def test_decision_date_is_end_minus_the_longer_of_notice_and_60_days(pack, end, notice, decide_by):
    (row, ics) = pack.act("lease_01.pdf", {**good(end_date=end, notice_days=notice), **meta()}, {"_today": date(2026, 11, 20)}, None)
    assert row["sheet"] == "Leases" and row["values"]["Renewal decision by"] == decide_by
    assert f"DTSTART;VALUE=DATE:{decide_by.replace('-', '')}" in ics["content"]


def test_leases_row_and_reminder_file(pack):
    rows = pack.act("lease_01.pdf", {**good(), **meta("renewal_due")}, {"_today": date(2026, 11, 20)}, None)
    row = next(r for r in rows if r["kind"] == "row")["values"]
    assert row["Tenants"] == "Isabel Crowe, Tom Crowe" and row["Renewal option"] == "yes" and row["Renewal due soon"] == "yes"
    assert row["Special conditions"] == "No pets without written consent"
    ics = next(r for r in rows if r["kind"] == "file")
    assert ics["folder"] == "reminders" and ics["name"] == "lease_01_renewal_decision.ics"
    text = ics["content"].replace("\r\n ", "")          # undo the RFC 5545 line folding of long lines
    assert text.startswith("BEGIN:VCALENDAR\r\n") and "BEGIN:VEVENT" in text and "DTSTAMP:20261120T000000Z" in text
    assert "SUMMARY:REMINDER: Lease renewal decision: Unit 3\\, 44 Starling Street\\, Footscray VIC 3011" in text
    assert "nothing has been sent or booked" in text


def test_end_to_end_with_a_mock_backend(pack, tmp_path):
    summary, res, backend, out = run_real_pack("property_leases", tmp_path)
    assert (summary["total"], summary["auto"], summary["human"]) == (8, 6, 2)
    assert res["lease_06.pdf"]["reasons"] == ["missing_notice"]
    assert res["lease_07.pdf"]["reasons"] == ["bad_term"]
    assert res["lease_01.pdf"]["route"] == "auto" and res["lease_01.pdf"]["reasons"] == ["renewal_due"]
    assert res["lease_05.pdf"]["route"] == "auto" and res["lease_05.pdf"]["reasons"] == ["renewal_due"]
    assert res["lease_02.pdf"]["reasons"] == []
    assert load_workbook(out / "report.xlsx")["Leases"].max_row == 1 + 6
    assert sorted(p.name for p in (out / "reminders").iterdir()) == [
        f"lease_0{n}_renewal_decision.ics" for n in (1, 2, 3, 4, 5, 8)]
    assert "DTSTART;VALUE=DATE:20261202" in (out / "reminders" / "lease_01_renewal_decision.ics").read_text()
    # The picture-only lease went to the model as an image; the others as text.
    calls = backend.extract_calls()
    assert [c["image"] is not None for c in calls] == [False] * 7 + [True]
    assert calls[7]["image"][1] == "image/png"


def test_picture_only_lease_goes_to_a_person_when_the_image_path_is_unavailable(pack, tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    summary, res, backend, out = run_real_pack("property_leases", tmp_path, cfg=make_cfg(image_mode="tesseract"))
    assert res["lease_08.pdf"]["route"] == "human" and res["lease_08.pdf"]["reasons"] == ["no_text_layer"]
    assert len(backend.extract_calls()) == 7                                      # the picture-only lease was not sent
    assert not (out / "reminders" / "lease_08_renewal_decision.ics").exists()
    items = inputs.load_items("pdf", PACK_DIR, "inbox/lease_08.pdf", "tesseract")
    assert items[0].preset_reason == "no_text_layer"
