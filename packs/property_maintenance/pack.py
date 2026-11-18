"""property_maintenance: tenant maintenance emails -> routed work-order drafts. Nothing is ever sent."""
from pathlib import Path

from engine import checks as ck

NAME = "property_maintenance"
TITLE = "Maintenance requests"
ORG = "Laneway Property Management (fictional)"
INPUT_GLOB = "inbox/*.eml"
INPUT_KIND = "email"
DRAFTS = False          # work orders and the safety reply are fixed templates filled by code, not by Claude
ACT_ON_HUMAN = True     # a hazard gets a safety reply, and an urgent job gets a work-order draft, even though a person is told

HAZARD_STEPS = {
    "gas_smell": ("a gas smell",
                  "Do not use light switches, flames or electrical items. Open doors and windows if it is safe to do so, "
                  "leave the property, and call [EMERGENCY NUMBER] from outside."),
    "electrical_hazard": ("an electrical hazard",
                          "Do not touch the item. If it is safe to do so, turn off the power at the switchboard and keep "
                          "everyone away from it. If anyone is hurt or there is smoke or fire, call [EMERGENCY NUMBER]."),
    "flooding": ("flooding",
                 "If it is safe to do so, turn off the water at the mains and the power to the affected area. Keep "
                 "everyone away from water near electrical items. If anyone is in danger, call [EMERGENCY NUMBER]."),
}


def _norm(text):
    return " ".join(str(text).casefold().split())


def find_property(hint, properties):
    """The one property the tenant's hint points to, or None (no hint, no match, or more than one match)."""
    if not hint or not str(hint).strip():
        return None
    h = _norm(hint)
    found = [p for p in properties if _norm(p["property_id"]) in h or _norm(p["address"]) in h]
    if not found and len(h) >= 6:
        found = [p for p in properties if h in _norm(p["address"])]
    return found[0] if len(found) == 1 else None


def load_reference(pack_dir):
    ref = Path(pack_dir) / "reference"
    return {"properties": ck.read_csv(ref / "properties.csv"), "trades": ck.index_csv(ref / "trades.csv", "trade")}


def checks(item_id, data, ref):
    reasons = []
    if data["hazard"] != "none":
        reasons.append("safety")
    if data["urgency"] == "urgent":
        reasons.append("urgent")
    if find_property(data["property_hint"], ref["properties"]) is None:
        reasons.append("unknown_property")
    if data["issue_type"] == "other":
        reasons.append("category_other")
    if data["needs_more_info"]:
        reasons.append("needs_more_info")
    return reasons


def route(data, reasons):
    return "human" if reasons else "auto"


def _safety_reply(item_id, data, prop):
    what, steps = HAZARD_STEPS[data["hazard"]]
    tenant = prop["tenant"] if prop else "[TENANT NAME]"
    text = (f"DRAFT - NOT SENT\n"
            f"To: {tenant}\n"
            f"Subject: Your maintenance request: please read this first\n\n"
            f"Hello {tenant},\n\n"
            f"Thank you for telling us about {what}. Your safety comes first. Please do this now:\n\n"
            f"{steps}\n\n"
            f"We have passed your request to a property manager, who will contact you. "
            f"[STAFF TO CONFIRM: who will call and when]\n\n"
            f"Laneway Property Management\n")
    return {"kind": "file", "folder": "drafts", "name": f"{Path(item_id).stem}_safety_reply.txt", "content": text}


def _work_order(item_id, data, prop, trade):
    urgent = data["urgency"] == "urgent"
    text = (f"DRAFT - NOT SENT\n"
            f"{'URGENT ' if urgent else ''}WORK ORDER\n\n"
            f"To: {trade['contractor']} <{trade['email']}>\n"
            f"Trade: {data['issue_type']}\n"
            f"Reference: {item_id}\n\n"
            f"Property: {prop['address']} ({prop['property_id']})\n"
            f"Tenant: {prop['tenant']}\n"
            f"Issue: {data['summary']}\n"
            f"Access: {data['access_notes'] or '[STAFF TO CONFIRM: access arrangements]'}\n"
            f"Approval limit: ${prop['approval_limit']}. Do not go over this without written approval "
            f"[STAFF TO CONFIRM: approval]\n")
    return {"kind": "file", "folder": "work_orders", "name": f"{Path(item_id).stem}.txt", "content": text}


def act(item_id, data, ref, draft_fn):
    prop = find_property(data["property_hint"], ref["properties"])
    if data["hazard"] != "none":
        return [_safety_reply(item_id, data, prop)]
    # Only a clean routine job, or an urgent job with nothing else wrong, gets a work order.
    if [r for r in data["_meta"]["reasons"] if r != "urgent"]:
        return []
    trade = ref["trades"].get(data["issue_type"])
    if prop is None or trade is None:
        raise ValueError(f"no property or trade for {item_id}")
    return [_work_order(item_id, data, prop, trade)]
