"""property_leases: lease PDFs -> terms, checked in code, with a renewal-decision reminder file. Nothing is sent."""
from datetime import datetime, timedelta
from pathlib import Path

from engine import checks as ck
from engine.ics import make_ics

NAME = "property_leases"
TITLE = "Lease extraction"
ORG = "Laneway Property Management (fictional)"
INPUT_GLOB = "inbox/*.pdf"
INPUT_KIND = "pdf"
DRAFTS = False

RENEWAL_WINDOW_DAYS = 90
MIN_NOTICE_DAYS = 60          # the decision date uses at least this many days of notice


def load_reference(pack_dir):
    return {}


def checks(item_id, data, ref):
    reasons = []
    if not ck.date_order_ok(data["start_date"], data["end_date"], strict=True):
        reasons.append("bad_term")                 # the end is not after the start, or a date cannot be read
    rent = ck.to_decimal(data["rent_amount"])
    if rent is None or rent <= 0:
        reasons.append("no_rent")
    if data["notice_days"] is None:
        reasons.append("missing_notice")
    end = ck.parse_date(data["end_date"])
    if end is not None and 0 <= (end - ref["_today"]).days <= RENEWAL_WINDOW_DAYS:
        reasons.append("renewal_due")              # information only: it is not a reason on its own
    return reasons


def route(data, reasons):
    blocking = [r for r in reasons if r != "renewal_due"]
    return "human" if blocking else "auto"


def decision_date(data):
    """The end date minus the longer of the notice period and 60 days."""
    end = ck.parse_date(data["end_date"])
    return end - timedelta(days=max(int(data["notice_days"]), MIN_NOTICE_DAYS))


def act(item_id, data, ref, draft_fn):
    decide_by = decision_date(data)
    tenants = ", ".join(data["tenant_names"])
    renewal_due = "renewal_due" in data["_meta"]["reasons"]
    row = {"Tenants": tenants, "Property": data["property_address"], "Start": data["start_date"],
           "End": data["end_date"], "Rent": data["rent_amount"], "Frequency": data["rent_frequency"],
           "Bond": data["bond_amount"], "Renewal option": "yes" if data["renewal_option"] else "no",
           "Notice (days)": data["notice_days"], "Renewal decision by": decide_by.isoformat(),
           "Renewal due soon": "yes" if renewal_due else "no", "Special conditions": "; ".join(data["special_conditions"])}
    stem = Path(item_id).stem
    ics = make_ics(
        f"{stem}-renewal", f"Lease renewal decision: {data['property_address']}", decide_by,
        datetime.combine(ref["_today"], datetime.min.time()),
        f"Tenants: {tenants}. Lease ends {data['end_date']}. Notice period {data['notice_days']} days. "
        f"Decide whether to renew by this date. This is a reminder only: nothing has been sent or booked.")
    return [{"kind": "row", "sheet": "Leases", "values": row},
            {"kind": "file", "folder": "reminders", "name": f"{stem}_renewal_decision.ics", "content": ics}]
