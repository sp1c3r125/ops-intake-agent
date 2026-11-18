"""finance_receipts: every check fires on crafted data, clean data passes, and one end-to-end run."""
from datetime import date

import pytest
from openpyxl import load_workbook

from engine import pipeline
from tests.helpers import PACKS, run_real_pack

PACK_DIR = PACKS / "finance_receipts"


@pytest.fixture(scope="module")
def pack():
    return pipeline.load_pack(PACK_DIR)


def good(**over):
    d = {"merchant": "Fitzroy Corner Cafe", "date": "2026-11-12", "currency": "AUD", "subtotal": 27.5, "tax": 2.75,
         "total": 30.25, "payment_method": "card", "category": "meals", "line_items": [], "confidence": 0.95}
    d.update(over)
    return d


def reasons(pack, data, item="receipt_01.png", claim="30.25", today=date(2026, 11, 20)):
    ref = pack.load_reference(PACK_DIR)
    if claim is not None:
        ref["claims"][item.casefold()] = {"file": item, "staff_id": "S1", "claimed_amount": claim}
    else:
        ref["claims"].pop(item.casefold(), None)
    ref["_today"], ref["_seen"] = today, set()
    return pack.checks(item, {**data, "_meta": {}}, ref)


def test_clean_receipt_passes(pack):
    assert reasons(pack, good()) == []


@pytest.mark.parametrize("data, claim, expected", [
    (good(total=31.00), "31.00", ["sum_mismatch"]),
    (good(total=30.27), "30.27", []),                                   # 0.02 apart is allowed
    (good(total=30.28), "30.28", ["sum_mismatch"]),
    (good(subtotal=50.0, tax=7.5, total=57.5), "57.50", ["gst_mismatch"]),
    (good(subtotal=27.5, tax=2.79, total=30.29), "30.29", []),          # GST within 0.05
    (good(subtotal=27.5, tax=2.81, total=30.31), "30.31", ["gst_mismatch"]),
    (good(subtotal=30.25, tax=0, total=30.25), "30.25", ["no_gst"]),
    (good(date="2026-11-21"), "30.25", ["future_date"]),
    (good(date="2026-08-22"), "30.25", []),                             # exactly 90 days old
    (good(date="2026-08-21"), "30.25", ["stale_receipt"]),
    (good(date="12/11/2026"), "30.25", ["bad_date"]),
    (good(), "99.00", ["amount_mismatch"]),
    (good(total=342.10, subtotal=311.0, tax=31.1), "342.10", ["over_limit"]),
    (good(total=300.0, subtotal=272.73, tax=27.27), "300.00", []),     # exactly 300 is not over
    (good(category="other"), "30.25", ["category_other"]),
    (good(total=None), "30.25", ["missing_field"]),                     # cut off: nothing else can be judged
    (good(merchant=None), "30.25", ["missing_field"]),
    (good(date=None), "30.25", ["missing_field"]),
    (good(tax=None), "30.25", ["missing_field"]),
])
def test_each_check_fires(pack, data, claim, expected):
    assert reasons(pack, data, claim=claim) == expected


def test_no_claim_on_file(pack):
    assert reasons(pack, good(), claim=None) == ["no_claim"]


def test_duplicate_is_the_second_sighting(pack):
    ref = pack.load_reference(PACK_DIR)
    ref["_today"], ref["_seen"] = date(2026, 11, 20), set()
    ref["claims"]["a.png"] = {"claimed_amount": "30.25"}
    ref["claims"]["b.png"] = {"claimed_amount": "30.25"}
    assert pack.checks("a.png", {**good(), "_meta": {}}, ref) == []
    assert pack.checks("b.png", {**good(merchant="FITZROY  corner CAFE"), "_meta": {}}, ref) == ["duplicate"]


def test_route_and_act_on_fixed_data(pack):
    assert pack.route(good(), []) == "auto" and pack.route(good(), ["over_limit"]) == "human"
    rows = pack.act("receipt_01.png", good(), {}, None)
    sheet = next(r for r in rows if r["kind"] == "row")
    csv_row = next(r for r in rows if r["kind"] == "csv")
    assert sheet["sheet"] == "Approved expenses" and sheet["values"]["Payee"] == "Fitzroy Corner Cafe"
    assert csv_row["name"] == "expenses_export.csv"
    assert list(csv_row["values"]) == ["Date", "Payee", "Amount", "Tax", "Category"]
    assert csv_row["values"] == {"Date": "2026-11-12", "Payee": "Fitzroy Corner Cafe", "Amount": 30.25,
                                 "Tax": 2.75, "Category": "meals"}


def test_end_to_end_with_a_mock_backend(pack, tmp_path):
    summary, res, backend, out = run_real_pack("finance_receipts", tmp_path)
    assert summary["total"] == 12 and summary["auto"] == 7 and summary["human"] == 5
    assert [r for r in res if res[r]["route"] == "auto"] == [f"receipt_0{n}.png" for n in range(1, 8)]
    assert res["receipt_08.png"]["reasons"] == ["low_confidence"]                      # blurry
    assert res["receipt_09.png"]["reasons"] == ["missing_field", "low_confidence"]     # total cut off
    assert res["receipt_10.png"]["reasons"] == ["duplicate"]
    assert res["receipt_11.png"]["reasons"] == ["over_limit"]
    assert res["receipt_12.png"]["reasons"] == ["gst_mismatch"]
    # Images went to the model as image blocks (IMAGE_MODE=vision); no draft calls (DRAFTS is False).
    assert len(backend.extract_calls()) == 12 and backend.draft_calls() == []
    assert all(c["image"] and c["image"][1] == "image/png" for c in backend.extract_calls())
    # Outputs
    assert load_workbook(out / "report.xlsx")["Approved expenses"].max_row == 1 + 7
    lines = (out / "expenses_export.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Date,Payee,Amount,Tax,Category" and len(lines) == 8
    assert lines[1] == "2026-11-12,Fitzroy Corner Cafe,30.25,2.75,meals"
    assert (out / "dashboard.html").exists()
