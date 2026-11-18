"""A tiny pack used only by the engine tests. It is not a real pack and lives outside packs/."""
from engine import checks as ck
from engine.drafts import DraftRejected
from engine.pipeline import default_route

NAME = "engine_pack"
TITLE = "Engine test pack"
ORG = "Testco (fictional)"
INPUT_GLOB = "inbox/*.txt"
INPUT_KIND = "text"
DRAFTS = True


def load_reference(pack_dir):
    return {"vendors": ck.index_csv(pack_dir / "reference" / "vendors.csv", "vendor")}


def checks(item_id, data, ref):
    reasons = []
    if data["summary"] == "RAISE_CHECK":
        raise RuntimeError("bug in checks")
    if data["kind"] == "invoice":
        if not ck.money_sum_ok([data["subtotal"], data["tax"]], data["total"]):
            reasons.append("sum_mismatch")
        if ck.is_duplicate(ref, data["vendor"], data["total"]):
            reasons.append("duplicate")
    d = ck.parse_date(data["date"])
    if d and d > ref["_today"]:
        reasons.append("future_date")
    if data["vendor"]:
        row = ck.lookup(ref["vendors"], data["vendor"])
        if row is None:
            reasons.append("unknown_vendor")
        elif row["status"] == "closed":
            reasons.append("closed_vendor")
    return reasons


def route(data, reasons):
    if data["summary"] == "RAISE_ROUTE":
        raise RuntimeError("bug in route")
    if data["summary"] == "BAD_ROUTE":
        return "maybe"
    if data["summary"] == "FORCE_AUTO":
        return "auto"
    if data["kind"] == "spam":
        return "skip"
    return default_route(reasons)


def act(item_id, data, ref, draft_fn):
    if data["summary"] == "RAISE_ACT":
        raise RuntimeError("bug in act")
    if data["summary"] == "BAD_ACT_OUTPUT":
        return "not a list"
    if data["kind"] == "invoice":
        return [{"kind": "row", "sheet": "Approved", "values": {"Vendor": data["vendor"], "Total": data["total"]}},
                {"kind": "csv", "name": "export.csv", "values": {"Payee": data["vendor"], "Amount": data["total"]}}]
    draft = draft_fn("Thank them and say we will check.", {"vendor": data["vendor"]})
    if data["summary"] == "REJECT_DRAFT":
        raise DraftRejected("draft_promise")
    return [{"kind": "file", "folder": "drafts", "name": f"{item_id}.txt", "content": draft}]


def _by_kind(results):
    counts = {}
    for r in results:
        k = (r["data"] or {}).get("kind", "none")
        counts[k] = counts.get(k, 0) + 1
    return [{"Kind": k, "Items": v} for k, v in sorted(counts.items())]


EXTRA_SHEETS = {"By kind": _by_kind}
