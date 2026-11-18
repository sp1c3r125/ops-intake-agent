"""logistics_shipments: customer emails to a freight company -> triage. Replies are drafts and never sent.

Claude classifies the email and writes the wording of a reply. The shipment status in a reply comes from the
shipment list, inserted by code.
"""
from pathlib import Path

from engine import checks as ck

NAME = "logistics_shipments"
TITLE = "Shipment email triage"
ORG = "Kestrel Freight (fictional), customer service"
INPUT_GLOB = "inbox/*.eml"
INPUT_KIND = "email"
DRAFTS = True

NEEDS_CONSIGNMENT = {"delay_query", "damage_report", "address_change", "delivery_confirmation", "customs_hold"}
DRAFT_CATEGORIES = {"delay_query", "delivery_confirmation", "pickup_request"}
STATUS_TEXT = {"delivered": "it has been delivered", "in_transit": "it is in transit", "delayed": "it is delayed",
               "customs_hold": "it is being held for customs clearance", "awaiting_pickup": "it is awaiting pickup"}


def load_reference(pack_dir):
    shared = Path(pack_dir).parent / "_shared" / "kestrel_shipments.csv"
    return {"shipments": ck.index_csv(shared, "consignment_no")}


def checks(item_id, data, ref):
    category = data["category"]
    if category == "spam":
        return []
    reasons = []
    if category == "damage_report":
        reasons += ["damage_report", "urgent"]
    elif category == "customs_hold":
        reasons += ["customs_hold", "urgent"]
    elif category == "address_change":
        reasons.append("verify_identity")        # never act on an address change without checking who is asking
    elif category == "other":
        reasons.append("category_other")
    if (category in NEEDS_CONSIGNMENT or data["consignment_no"]) and \
            ck.lookup(ref["shipments"], data["consignment_no"]) is None:
        reasons.append("unknown_consignment")
    if data["needs_more_info"]:
        reasons.append("needs_more_info")
    return reasons


def route(data, reasons):
    if data["category"] == "spam":
        return "skip"                            # no draft. (The engine still sends low-confidence spam to a person.)
    return "human" if reasons else "auto"


def status_line(shipment):
    return (f"Consignment {shipment['consignment_no']} for {shipment['consignee']}, {shipment['suburb']}: "
            f"{STATUS_TEXT.get(shipment['status'], 'its status is ' + shipment['status'])}. "
            f"Expected delivery: {shipment['expected_date']}.")


def act(item_id, data, ref, draft_fn):
    if data["category"] not in DRAFT_CATEGORIES:
        return []
    shipment = ck.lookup(ref["shipments"], data["consignment_no"])
    if data["category"] == "pickup_request" and shipment is None:
        text = draft_fn("Write a short, polite reply to a customer asking for a pickup. Acknowledge the request. "
                        "Do not promise a pickup time or price: write [STAFF TO CONFIRM: pickup date and time].",
                        {"request": data["summary"]})
    else:
        text = draft_fn("Write a short, polite reply to a customer asking about their shipment. Put exactly "
                        "{STATUS} on its own line where the shipment status belongs. Do not state any status, "
                        "date, location or reason for a delay yourself. If you cannot answer something, write "
                        "[STAFF TO CONFIRM: what is needed].",
                        {"customer_question": data["summary"], "consignment_no": data["consignment_no"]})
    inserted = status_line(shipment) if shipment else "[STAFF TO CONFIRM: shipment status]"
    if "{STATUS}" in text:
        text = text.replace("{STATUS}", inserted)
    elif shipment:
        text = f"{text.rstrip()}\n\nShipment status (from our system): {inserted}\n"
    return [{"kind": "file", "folder": "drafts", "name": f"{Path(item_id).stem}.txt", "content": text}]
