"""logistics_pod: photos of signed delivery dockets -> proof of delivery, checked against the shipment list."""
from pathlib import Path

from engine import checks as ck

NAME = "logistics_pod"
TITLE = "Proof of delivery"
ORG = "Kestrel Freight (fictional)"
INPUT_GLOB = "inbox/*.png"
INPUT_KIND = "image"
DRAFTS = False
ACT_ON_HUMAN = True      # a damage item goes to a person AND gets a damage-claim note (a fixed template, code not Claude)


def load_reference(pack_dir):
    shared = Path(pack_dir).parent / "_shared" / "kestrel_shipments.csv"
    return {"shipments": ck.index_csv(shared, "consignment_no")}


def checks(item_id, data, ref):
    reasons = []
    shipment = ck.lookup(ref["shipments"], data["consignment_no"])
    if shipment is None:
        reasons.append("unknown_consignment")

    delivered = ck.parse_datetime(data["delivered_at"])
    if delivered is None or delivered.date() > ref["_today"]:
        reasons.append("bad_date")                       # unreadable, or in the future
    elif shipment is not None and not ck.date_order_ok(shipment["dispatch_date"], delivered.date()):
        reasons.append("bad_date")                       # delivered before it was dispatched

    if not data["signature_present"]:
        reasons.append("no_signature")
    if data["damage_noted"]:
        reasons.append("damage")
    if shipment is not None and data["packages_count"] != int(shipment["packages"]):
        reasons.append("count_mismatch")
    return reasons


def route(data, reasons):
    return "human" if reasons else "auto"


def _claim_note(item_id, data, shipment):
    consignee = f"{shipment['consignee']}, {shipment['suburb']}" if shipment else "[STAFF TO CONFIRM: consignee]"
    expected = shipment["packages"] if shipment else "[STAFF TO CONFIRM]"
    text = (f"DRAFT - NOT SENT\n"
            f"DAMAGE CLAIM NOTE\n\n"
            f"Consignment: {data['consignment_no'] or '[STAFF TO CONFIRM: consignment number]'}\n"
            f"Consignee: {consignee}\n"
            f"Delivered: {data['delivered_at'] or '[STAFF TO CONFIRM: date and time]'}\n"
            f"Received by: {data['recipient_name'] or '[STAFF TO CONFIRM]'}\n"
            f"Packages on docket: {data['packages_count']} (shipment list: {expected})\n"
            f"Damage written on the docket: {data['damage_note'] or '[STAFF TO CONFIRM: no note was readable]'}\n"
            f"Signature present: {'yes' if data['signature_present'] else 'no'}\n"
            f"Docket file: {item_id}\n\n"
            f"Next steps (staff): [STAFF TO CONFIRM: photograph the goods, hold the packaging, open a claim]\n")
    return {"kind": "file", "folder": "work_orders", "name": f"{Path(item_id).stem}_damage_claim.txt", "content": text}


def act(item_id, data, ref, draft_fn):
    meta = data["_meta"]
    shipment = ck.lookup(ref["shipments"], data["consignment_no"])
    rows = []
    if "damage" in meta["reasons"]:
        rows.append(_claim_note(item_id, data, shipment))
    if meta["route"] == "auto":
        rows.append({"kind": "row", "sheet": "Delivered", "values": {
            "Consignment": data["consignment_no"], "Consignee": shipment["consignee"],
            "Delivered at": data["delivered_at"], "Received by": data["recipient_name"],
            "Packages": data["packages_count"], "Status": "POD OK"}})
    return rows
