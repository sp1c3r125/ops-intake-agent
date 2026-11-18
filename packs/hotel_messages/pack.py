"""hotel_messages: guest emails to a hotel -> triage and reply drafts. Never sends. Never changes a stay.

reference/stays.csv is a lookup only. Facts in a draft (guest name, dates, room type) come from that file, found
by the booking reference, and never from the email text.
"""
from pathlib import Path

from engine import checks as ck

NAME = "hotel_messages"
TITLE = "Guest message triage"
ORG = "Saltmarsh Suites (fictional)"
INPUT_GLOB = "inbox/*.eml"
INPUT_KIND = "email"
DRAFTS = True

PLACEHOLDER = "[STAFF TO CONFIRM"
DRAFT_CATEGORIES = {
    "late_checkout": ("Write a short, polite reply to a guest asking for a late checkout. Do not say yes or no and do "
                      "not quote a fee: write [STAFF TO CONFIRM: whether a late checkout is available, and any fee].",
                      "[STAFF TO CONFIRM: whether a late checkout is available, and any fee]"),
    "early_checkin": ("Write a short, polite reply to a guest asking for an early check-in. Do not say yes or no and "
                      "do not quote a fee: write [STAFF TO CONFIRM: whether the room will be ready, and any fee].",
                      "[STAFF TO CONFIRM: whether the room will be ready early, and any fee]"),
    "special_request": ("Write a short, polite reply acknowledging the guest's request. Do not promise it: write "
                        "[STAFF TO CONFIRM: whether we can arrange this].",
                        "[STAFF TO CONFIRM: whether we can arrange this]"),
    "invoice_request": ("Write a short, polite reply saying a tax invoice will be sent. State no amounts or dates: "
                        "write [STAFF TO CONFIRM: invoice details and who to send it to].",
                        "[STAFF TO CONFIRM: invoice details and who to send it to]"),
    "lost_item": ("Write a short, polite reply to a guest about an item they say they left behind. Say staff will "
                  "check. Do not say it has been found and do not promise to return it: write "
                  "[STAFF TO CONFIRM: whether the item has been found, and how it can be returned].",
                  "[STAFF TO CONFIRM: whether the item has been found, and how it can be returned]"),
}


def load_reference(pack_dir):
    return {"stays": ck.index_csv(Path(pack_dir) / "reference" / "stays.csv", "booking_ref")}


def checks(item_id, data, ref):
    category = data["category"]
    if category == "spam":
        return []
    reasons = []
    if category in ("complaint", "safety_issue"):
        reasons += [category, "urgent"]          # to the duty manager, now
    elif category == "stay_change":
        reasons.append("stay_change")            # changes to a stay are always made by a person
    elif category == "other":
        reasons.append("category_other")
    if ck.lookup(ref["stays"], data["booking_ref"]) is None:
        reasons.append("unknown_booking")
    if data["needs_more_info"]:
        reasons.append("needs_more_info")
    return reasons


def route(data, reasons):
    if data["category"] == "spam":
        return "skip"
    return "human" if reasons else "auto"


def act(item_id, data, ref, draft_fn):
    if data["category"] not in DRAFT_CATEGORIES:
        return []
    stay = ck.lookup(ref["stays"], data["booking_ref"])
    instructions, fallback = DRAFT_CATEGORIES[data["category"]]
    text = draft_fn(instructions, {"guest_name": stay["guest_name"], "arrival": stay["arrival"],
                                   "departure": stay["departure"], "room_type": stay["room_type"],
                                   "guest_request": data["summary"]})
    if PLACEHOLDER not in text:
        text = f"{text.rstrip()}\n\n{fallback}\n"       # every reply needs a person to confirm the facts
    out = [{"kind": "file", "folder": "drafts", "name": f"{Path(item_id).stem}.txt", "content": text}]
    if data["category"] == "lost_item":
        out.append({"kind": "row", "sheet": "Lost items", "values": {
            "Booking": stay["booking_ref"], "Guest": stay["guest_name"], "Room type": stay["room_type"],
            "Departure": stay["departure"], "Item reported": data["summary"],
            "Reported on": ref["_today"].isoformat(), "Status": "To check"}})
    return out
