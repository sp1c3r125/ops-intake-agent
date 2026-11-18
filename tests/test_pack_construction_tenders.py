"""construction_tenders: scope, closing-date checks (business days), register rows, reminder files, end to end."""
from datetime import date

import pytest
from openpyxl import load_workbook

from engine import pipeline
from tests.helpers import PACKS, run_real_pack

PACK_DIR = PACKS / "construction_tenders"
TODAY = date(2026, 11, 20)      # a Friday


@pytest.fixture(scope="module")
def pack():
    return pipeline.load_pack(PACK_DIR)


def good(**over):
    d = {"project_name": "Docklands Apartments Stage 2", "client_name": "Harbourline Constructions",
         "site_suburb": "Docklands", "trades_in_scope": ["hvac", "mechanical"], "closing_datetime": "2026-12-04 14:00",
         "site_visit_datetime": "2026-11-24 10:00", "documents_link": "https://tenders.example/x",
         "contact_email": "p@example.example", "summary": "HVAC tender.", "confidence": 0.95}
    d.update(over)
    return d


def check(pack, data, today=TODAY):
    return pack.checks("t.eml", {**data, "_meta": {}}, {"_today": today})


@pytest.mark.parametrize("over, expected", [
    ({}, []),
    ({"trades_in_scope": ["hvac"]}, []),
    ({"trades_in_scope": ["mechanical", "plumbing"]}, []),
    ({"trades_in_scope": ["electrical", "plumbing"]}, ["out_of_scope"]),
    ({"trades_in_scope": ["civil", "other"]}, ["out_of_scope"]),
    ({"trades_in_scope": []}, ["out_of_scope"]),
    ({"closing_datetime": None}, ["no_closing_date"]),
    ({"closing_datetime": "soon"}, ["no_closing_date"]),
    ({"closing_datetime": "2026-11-19 17:00"}, ["closed"]),                       # yesterday
    ({"closing_datetime": "2026-11-20 17:00"}, ["closing_soon", "urgent"]),       # today: 0 business days left
    ({"closing_datetime": "2026-11-21 12:00"}, ["closing_soon", "urgent"]),       # tomorrow (a Saturday)
    ({"closing_datetime": "2026-11-23 17:00"}, ["closing_soon", "urgent"]),       # Monday: 1 business day
    ({"closing_datetime": "2026-11-24 17:00"}, ["closing_soon", "urgent"]),       # Tuesday: 2
    ({"closing_datetime": "2026-11-25 17:00"}, []),                               # Wednesday: 3, not fewer than 3
    ({"documents_link": None}, ["no_documents"]),
    ({"documents_link": ""}, ["no_documents"]),
    ({"trades_in_scope": ["civil"], "closing_datetime": None, "documents_link": None},
     ["out_of_scope", "no_closing_date", "no_documents"]),
])
def test_each_check_fires(pack, over, expected):
    assert check(pack, good(**over)) == expected


def test_business_days_not_calendar_days_and_demo_today(pack):
    # Closing Monday 7 December: from Friday 4 December that is 1 business day (soon); from Monday 30 Nov, 5 (fine).
    data = good(closing_datetime="2026-12-07 10:00")
    assert check(pack, data, today=date(2026, 12, 4)) == ["closing_soon", "urgent"]
    assert check(pack, data, today=date(2026, 11, 30)) == []


def meta(*reasons):
    return {"_meta": {"reasons": list(reasons), "route": "human" if reasons else "auto"}}


def reminders(rows):
    return {r["name"]: r["content"].replace("\r\n ", "") for r in rows if r["kind"] == "file"}


def test_a_clean_tender_gets_a_register_row_and_three_reminders(pack):
    rows = pack.act("01_docklands.eml", {**good(), **meta()}, {"_today": TODAY}, None)
    row = next(r for r in rows if r["kind"] == "row")
    assert row["sheet"] == "Tender register" and row["values"]["Status"] == "Ready to price"
    assert row["values"]["Urgent"] == "no" and row["values"]["Trades"] == "hvac, mechanical"
    files = reminders(rows)
    assert sorted(files) == ["01_docklands_closing.ics", "01_docklands_site_visit.ics", "01_docklands_two_days_before.ics"]
    assert "DTSTART:20261124T100000" in files["01_docklands_site_visit.ics"]                 # the site visit, timed
    assert "DTSTART;VALUE=DATE:20261202" in files["01_docklands_two_days_before.ics"]        # Fri 4 Dec minus 2 business days
    assert "DTSTART:20261204T140000" in files["01_docklands_closing.ics"]                    # the closing time
    assert "SUMMARY:REMINDER: Tender closes: Docklands Apartments Stage 2" in files["01_docklands_closing.ics"]


def test_two_business_days_before_skips_the_weekend(pack):
    rows = pack.act("t.eml", {**good(closing_datetime="2026-12-07 10:00"), **meta()}, {"_today": TODAY}, None)
    assert "DTSTART;VALUE=DATE:20261203" in reminders(rows)["t_two_days_before.ics"]          # Mon 7 Dec -> Thu 3 Dec


def test_no_site_visit_means_no_site_visit_reminder(pack):
    rows = pack.act("t.eml", {**good(site_visit_datetime=None), **meta()}, {"_today": TODAY}, None)
    assert sorted(reminders(rows)) == ["t_closing.ics", "t_two_days_before.ics"]


def test_reminders_are_never_made_in_the_past(pack):
    rows = pack.act("t.eml", {**good(site_visit_datetime="2026-11-10 10:00"), **meta()}, {"_today": TODAY}, None)
    assert "t_site_visit.ics" not in reminders(rows)
    soon = pack.act("t.eml", {**good(closing_datetime="2026-11-21 12:00", site_visit_datetime=None),
                              **meta("closing_soon", "urgent")}, {"_today": TODAY}, None)
    assert sorted(reminders(soon)) == ["t_closing.ics"]                                        # 2 days before was Wednesday


def test_urgent_tender_is_marked_in_the_register_and_still_gets_a_closing_reminder(pack):
    rows = pack.act("t.eml", {**good(closing_datetime="2026-11-21 12:00"), **meta("closing_soon", "urgent")},
                    {"_today": TODAY}, None)
    values = next(r for r in rows if r["kind"] == "row")["values"]
    assert values["Status"] == "URGENT: closing soon" and values["Urgent"] == "yes"
    assert "DTSTART:20261121T120000" in reminders(rows)["t_closing.ics"]


@pytest.mark.parametrize("over, reasons, status", [
    ({"trades_in_scope": ["civil"]}, ["out_of_scope"], "Decline: confirm"),
    ({"closing_datetime": "2026-11-10 10:00"}, ["closed"], "Closed"),
    ({"closing_datetime": None}, ["no_closing_date"], "Find closing date"),
    ({}, ["low_confidence"], "Needs review"),
])
def test_register_row_but_no_reminders_when_we_cannot_rely_on_the_tender(pack, over, reasons, status):
    rows = pack.act("t.eml", {**good(**over), **meta(*reasons)}, {"_today": TODAY}, None)
    assert [r["kind"] for r in rows] == ["row"] and rows[0]["values"]["Status"] == status


def test_missing_documents_alone_does_not_stop_the_reminders(pack):
    rows = pack.act("t.eml", {**good(documents_link=None), **meta("no_documents")}, {"_today": TODAY}, None)
    assert len(reminders(rows)) == 3


def test_end_to_end_with_a_mock_backend(pack, tmp_path):
    summary, res, backend, out = run_real_pack("construction_tenders", tmp_path)
    assert (summary["total"], summary["auto"], summary["human"]) == (10, 6, 4)
    assert res["04_landscaping_civil.eml"]["reasons"] == ["out_of_scope"]
    assert res["05_closes_tomorrow.eml"]["reasons"] == ["closing_soon", "urgent"]
    assert res["06_no_date.eml"]["reasons"] == ["no_closing_date"]
    assert res["08_no_documents.eml"]["reasons"] == ["no_documents"]
    assert all(res[k]["route"] == "auto" for k in ("01_docklands_hvac.eml", "02_hospital_mechanical.eml",
                                                    "03_school_gym.eml", "07_injection.eml", "09_library.eml",
                                                    "10_brewery_cooling.eml"))
    # Every tender is on the register, including the ones a person must look at.
    ws = load_workbook(out / "report.xlsx")["Tender register"]
    header = [c.value for c in ws[1]]
    status = {row[0].value: row[header.index("Status") + 0].value for row in ws.iter_rows(min_row=2)}
    assert ws.max_row == 1 + 10 and status["04_landscaping_civil.eml"] == "Decline: confirm"
    assert status["05_closes_tomorrow.eml"] == "URGENT: closing soon" and status["07_injection.eml"] == "Ready to price"
    names = sorted(p.name for p in (out / "reminders").iterdir())
    assert "05_closes_tomorrow_closing.ics" in names and "05_closes_tomorrow_two_days_before.ics" not in names
    assert not any(n.startswith(("04_", "06_")) for n in names)                  # out of scope / no date: no reminders
    assert "01_docklands_hvac_site_visit.ics" in names and "03_school_gym_site_visit.ics" not in names
    assert len(names) == 19
    # The PDF tender summary was read: its dates reached the model inside the document.
    first = backend.extract_calls()[0]["user"]
    assert "Tenders close: Friday 4 December 2026 at 2:00pm" in first and first.startswith("<document>")
    # The injected tender is an ordinary hvac tender, and the register is not told to decline everything.
    assert load_workbook(out / "report.xlsx")["Tender register"]["A8"].value == "07_injection.eml"
