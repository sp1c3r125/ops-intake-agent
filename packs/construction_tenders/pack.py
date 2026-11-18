"""construction_tenders: tender invitation emails -> a tender register and reminder files. Nothing is sent.

The model reads the email (and any PDF tender summary). Code decides whether the tender is in scope, closed, or
closing soon, and writes the reminders.
"""
from datetime import datetime
from pathlib import Path

from engine import checks as ck
from engine.ics import make_ics

NAME = "construction_tenders"
TITLE = "Tender intake"
ORG = "Westgate Climate Services (fictional)"
INPUT_GLOB = "inbox/*.eml"
INPUT_KIND = "email"
DRAFTS = False
ACT_ON_HUMAN = True       # the register lists every tender, and a tender that closes soon still gets its reminders

OUR_TRADES = {"hvac", "mechanical"}
SOON_BUSINESS_DAYS = 3
# Reminders are only made when what we read is trustworthy: nothing but these reasons may be present.
REMINDER_OK_REASONS = {"closing_soon", "urgent", "no_documents"}


def load_reference(pack_dir):
    return {}


def checks(item_id, data, ref):
    reasons = []
    if not OUR_TRADES & set(data["trades_in_scope"]):
        reasons.append("out_of_scope")             # a person confirms the decline
    closing = ck.parse_datetime(data["closing_datetime"])
    if closing is None:
        reasons.append("no_closing_date")
    elif closing.date() < ref["_today"]:
        reasons.append("closed")
    elif ck.business_days_between(ref["_today"], closing.date()) < SOON_BUSINESS_DAYS:
        reasons += ["closing_soon", "urgent"]
    if not data["documents_link"]:
        reasons.append("no_documents")
    return reasons


def route(data, reasons):
    return "human" if reasons else "auto"


def _status(reasons):
    for reason, text in (("out_of_scope", "Decline: confirm"), ("closed", "Closed"), ("no_closing_date", "Find closing date"),
                         ("closing_soon", "URGENT: closing soon")):
        if reason in reasons:
            return text
    return "Needs review" if reasons else "Ready to price"


def act(item_id, data, ref, draft_fn):
    reasons = data["_meta"]["reasons"]
    today = ref["_today"]
    stem = Path(item_id).stem
    row = {"Project": data["project_name"], "Client": data["client_name"], "Site suburb": data["site_suburb"],
           "Trades": ", ".join(data["trades_in_scope"]), "Closing": data["closing_datetime"],
           "Site visit": data["site_visit_datetime"], "Documents": data["documents_link"],
           "Contact": data["contact_email"], "Status": _status(reasons),
           "Urgent": "yes" if "urgent" in reasons else "no", "Summary": data["summary"],
           "Reasons": ", ".join(reasons)}
    out = [{"kind": "row", "sheet": "Tender register", "values": row}]

    closing = ck.parse_datetime(data["closing_datetime"])
    if closing is None or not set(reasons) <= REMINDER_OK_REASONS:
        return out                                 # out of scope, closed, no date, or not sure we read it right
    stamp = datetime.combine(today, datetime.min.time())
    project = data["project_name"]

    def reminder(kind, summary, start, note, minutes=30):
        out.append({"kind": "file", "folder": "reminders", "name": f"{stem}_{kind}.ics",
                    "content": make_ics(f"{stem}-{kind}", summary, start, stamp, note, minutes)})

    visit = ck.parse_datetime(data["site_visit_datetime"])
    if visit is not None and visit.date() >= today:
        reminder("site_visit", f"Site visit: {project}", visit, f"Tender for {data['client_name']}. Closes {data['closing_datetime']}.", 60)
    two_before = ck.add_business_days(closing.date(), -2)
    if two_before >= today:
        reminder("two_days_before", f"Tender closes in 2 business days: {project}", two_before,
                 f"Closing {data['closing_datetime']}. Check pricing is on track.")
    reminder("closing", f"Tender closes: {project}", closing, f"Submit by {data['closing_datetime']}.", 15)
    return out
