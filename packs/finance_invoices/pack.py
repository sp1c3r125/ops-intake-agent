"""finance_invoices: supplier invoices (PDF with a text layer) -> data, matched to purchase orders in code."""
import re
from decimal import Decimal

from engine import checks as ck

NAME = "finance_invoices"
TITLE = "Supplier invoice intake"
ORG = "Copperleaf Advisory (fictional), accounts payable"
INPUT_GLOB = "inbox/*.pdf"
INPUT_KIND = "pdf"
DRAFTS = False

OVER_PO_FACTOR = Decimal("1.05")


def _name(s):
    """Supplier names compared without case, punctuation or a trailing 'Pty Ltd'."""
    s = re.sub(r"[^a-z0-9 ]", "", str(s).casefold())
    return re.sub(r"\s+(pty\s*)?(ltd|limited)?$", "", " ".join(s.split())).strip()


def load_reference(pack_dir):
    return {"po": ck.index_csv(pack_dir / "reference" / "po_register.csv", "po_number")}


def checks(item_id, data, ref):
    reasons = []
    if not ck.money_sum_ok([line["amount"] for line in data["line_items"]], data["subtotal"]):
        reasons.append("lines_mismatch")
    if not ck.money_sum_ok([data["subtotal"], data["tax"]], data["total"]):
        reasons.append("sum_mismatch")
    if not ck.date_order_ok(data["invoice_date"], data["due_date"]):
        reasons.append("bad_due_date")             # due before the invoice date, or a date that cannot be read

    if not data["po_number"]:
        reasons.append("no_po")
    else:
        po = ck.lookup(ref["po"], data["po_number"])
        if po is None:
            reasons.append("po_not_found")
        else:
            if po["status"].casefold() != "open":
                reasons.append("po_closed")
            if _name(po["supplier"]) != _name(data["supplier"]):
                reasons.append("supplier_mismatch")
            limit = ck.to_decimal(po["amount"])
            total = ck.to_decimal(data["total"])
            if limit is not None and total is not None and total > limit * OVER_PO_FACTOR:
                reasons.append("over_po")

    if ck.is_duplicate(ref, data["supplier"], data["invoice_number"]):
        reasons.append("duplicate")
    return reasons


def route(data, reasons):
    return "human" if reasons else "auto"


def act(item_id, data, ref, draft_fn):
    return []   # the Ready to pay sheet is built from all auto items, sorted by due date (EXTRA_SHEETS)


def ready_to_pay(results):
    rows = [r for r in results if r["route"] == "auto" and r["data"]]
    rows.sort(key=lambda r: (r["data"]["due_date"], r["item"]))
    return [{"Due date": r["data"]["due_date"], "Supplier": r["data"]["supplier"],
             "Invoice": r["data"]["invoice_number"], "PO": r["data"]["po_number"], "Total": r["data"]["total"],
             "File": r["item"]} for r in rows]


EXTRA_SHEETS = {"Ready to pay": ready_to_pay}
