"""finance_receipts: staff expense receipts (photos) -> data, checked in code."""
from decimal import Decimal

from engine import checks as ck

NAME = "finance_receipts"
TITLE = "Receipt to data"
ORG = "Copperleaf Advisory (fictional)"
INPUT_GLOB = "inbox/*.png"
INPUT_KIND = "image"
DRAFTS = False

OVER_LIMIT = Decimal("300")
STALE_DAYS = 90
GST_RATE = Decimal("0.10")
MUST_READ = ("merchant", "date", "subtotal", "tax", "total")


def load_reference(pack_dir):
    return {"claims": ck.index_csv(pack_dir / "reference" / "claims.csv", "file")}


def checks(item_id, data, ref):
    reasons = []
    today = ref["_today"]
    if any(data.get(k) is None for k in MUST_READ):
        reasons.append("missing_field")          # unreadable or cut off: a person looks at the photo

    subtotal, tax, total = (ck.to_decimal(data.get(k)) for k in ("subtotal", "tax", "total"))
    if None not in (subtotal, tax, total) and not ck.money_sum_ok([subtotal, tax], total, "0.02"):
        reasons.append("sum_mismatch")
    if None not in (subtotal, tax):
        if tax == 0:
            reasons.append("no_gst")
        elif not ck.money_close(tax, subtotal * GST_RATE, "0.05"):
            reasons.append("gst_mismatch")

    if data.get("date") is not None:
        d = ck.parse_date(data["date"])
        if d is None:
            reasons.append("bad_date")
        elif d > today:
            reasons.append("future_date")
        elif (today - d).days > STALE_DAYS:
            reasons.append("stale_receipt")

    claim = ck.lookup(ref["claims"], item_id)
    if claim is None:
        reasons.append("no_claim")               # a receipt nobody claimed
    elif total is not None and not ck.money_close(total, claim["claimed_amount"], "0"):
        reasons.append("amount_mismatch")

    if None not in (data.get("merchant"), data.get("date"), total) and ck.is_duplicate(
            ref, data["merchant"], data["date"], total):
        reasons.append("duplicate")
    if total is not None and total > OVER_LIMIT:
        reasons.append("over_limit")
    if data.get("category") == "other":
        reasons.append("category_other")
    return reasons


def route(data, reasons):
    return "human" if reasons else "auto"


def act(item_id, data, ref, draft_fn):
    export = {"Date": data["date"], "Payee": data["merchant"], "Amount": data["total"], "Tax": data["tax"],
              "Category": data["category"]}
    return [
        {"kind": "row", "sheet": "Approved expenses",
         "values": {**export, "Currency": data["currency"], "Payment method": data["payment_method"]}},
        {"kind": "csv", "name": "expenses_export.csv", "values": export},
    ]
