"""finance_invoices: every check fires on crafted data, clean data passes, and one end-to-end run."""
import pytest
from openpyxl import load_workbook

from engine import pipeline
from tests.helpers import PACKS, run_real_pack

PACK_DIR = PACKS / "finance_invoices"


@pytest.fixture(scope="module")
def pack():
    return pipeline.load_pack(PACK_DIR)


def good(**over):
    d = {"supplier": "Banksia Office Supplies Pty Ltd", "abn": "00 000 000 011", "invoice_number": "INV-2201",
         "invoice_date": "2026-10-30", "due_date": "2026-11-29", "po_number": "PO-7001", "currency": "AUD",
         "line_items": [{"description": "Paper", "qty": 20, "unit_price": 12.5, "amount": 250.0},
                        {"description": "Toner", "qty": 4, "unit_price": 85.0, "amount": 340.0}],
         "subtotal": 590.0, "tax": 59.0, "total": 649.0, "confidence": 0.95}
    d.update(over)
    return d


def check(pack, data, seen=None):
    ref = pack.load_reference(PACK_DIR)
    ref["_seen"] = seen if seen is not None else set()
    return pack.checks("x.pdf", {**data, "_meta": {}}, ref)


def test_clean_invoice_passes(pack):
    assert check(pack, good()) == []


@pytest.mark.parametrize("over, expected", [
    ({"subtotal": 600.0, "tax": 60.0, "total": 660.0}, ["lines_mismatch"]),           # lines add to 590, not 600
    ({"line_items": []}, ["lines_mismatch"]),
    ({"total": 650.0}, ["sum_mismatch"]),
    ({"total": 649.02}, []),                                                          # within 0.02
    ({"due_date": "2026-10-29"}, ["bad_due_date"]),                                    # due before invoice date
    ({"due_date": "2026-10-30"}, []),                                                  # same day is fine
    ({"due_date": "next month"}, ["bad_due_date"]),                                    # unreadable date is flagged
    ({"po_number": None}, ["no_po"]),
    ({"po_number": ""}, ["no_po"]),
    ({"po_number": "PO-9999"}, ["po_not_found"]),
    ({"po_number": "PO-7008"}, ["po_closed", "over_po"]),                              # closed PO (and only $400)
    ({"po_number": "PO-7002"}, ["supplier_mismatch"]),                                 # PO belongs to Kookaburra
    ({"supplier": "BANKSIA office supplies"}, []),                                     # name compared loosely
    ({"subtotal": 1090.91, "tax": 109.09, "total": 1200.0, "line_items": [
        {"description": "x", "qty": 1, "unit_price": 1090.91, "amount": 1090.91}]}, []),   # exactly the PO amount
    ({"subtotal": 1200.0, "tax": 60.0, "total": 1260.0, "line_items": [
        {"description": "x", "qty": 1, "unit_price": 1200.0, "amount": 1200.0}]}, []),     # exactly PO x 1.05: fine
    ({"subtotal": 1200.0, "tax": 60.01, "total": 1260.01, "line_items": [
        {"description": "x", "qty": 1, "unit_price": 1200.0, "amount": 1200.0}]}, ["over_po"]),
])
def test_each_check_fires(pack, over, expected):
    assert check(pack, good(**over)) == expected


def test_several_reasons_are_all_listed(pack):
    data = good(po_number="PO-9999", total=700.0, due_date="2026-10-01")
    assert check(pack, data) == ["sum_mismatch", "bad_due_date", "po_not_found"]


def test_duplicate_is_same_supplier_and_invoice_number(pack):
    seen = set()
    assert check(pack, good(), seen) == []
    assert check(pack, good(supplier="Banksia Office Supplies Pty Ltd "), seen) == ["duplicate"]
    assert check(pack, good(invoice_number="INV-2202"), seen) == []
    assert check(pack, good(supplier="Kookaburra Cleaning Services Pty Ltd", po_number="PO-7002"), seen) == []


def test_route_act_and_ready_to_pay_sheet(pack):
    assert pack.route(good(), []) == "auto" and pack.route(good(), ["no_po"]) == "human"
    assert pack.act("x.pdf", good(), {}, None) == []
    results = [
        {"item": "b.pdf", "route": "auto", "data": good(due_date="2026-12-05", invoice_number="B")},
        {"item": "a.pdf", "route": "auto", "data": good(due_date="2026-11-25", invoice_number="A")},
        {"item": "c.pdf", "route": "human", "data": good(due_date="2026-11-01", invoice_number="C")},
        {"item": "d.pdf", "route": "human", "data": None},
        {"item": "e.pdf", "route": "auto", "data": good(due_date="2026-11-25", invoice_number="E")},
    ]
    rows = pack.extra_sheets["Ready to pay"](results)
    assert [r["Invoice"] for r in rows] == ["A", "E", "B"]                       # by due date, then file name; no human items


def test_end_to_end_with_a_mock_backend(pack, tmp_path):
    summary, res, backend, out = run_real_pack("finance_invoices", tmp_path)
    assert (summary["total"], summary["auto"], summary["human"]) == (10, 6, 4)
    assert res["invoice_07.pdf"]["reasons"] == ["no_po"]
    assert res["invoice_08.pdf"]["reasons"] == ["over_po"]
    assert res["invoice_09.pdf"]["reasons"] == ["duplicate"]
    assert res["invoice_10.pdf"]["reasons"] == ["lines_mismatch"]
    assert all(res[f"invoice_0{n}.pdf"]["route"] == "auto" for n in range(1, 7))
    # PDFs with a text layer: the model is given the text (inside <document> tags), no image.
    calls = backend.extract_calls()
    assert len(calls) == 10 and backend.draft_calls() == []
    assert all(c["image"] is None and c["user"].startswith("<document>") for c in calls)
    assert "INV-2201" in calls[0]["user"] and "Purchase Order: PO-7001" in calls[0]["user"]
    # Ready to pay is sorted by due date.
    ws = load_workbook(out / "report.xlsx")["Ready to pay"]
    assert [row[0].value for row in ws.iter_rows(min_row=2)] == [
        "2026-11-20", "2026-11-29", "2026-12-02", "2026-12-05", "2026-12-09", "2026-12-10"]
    assert "Ready to pay" in (out / "dashboard.html").read_text(encoding="utf-8")
