"""logistics_pod: checks, the fixed damage-claim note, and one end-to-end run."""
from datetime import date

import pytest
from openpyxl import load_workbook

from engine import pipeline
from tests.helpers import PACKS, run_real_pack

PACK_DIR = PACKS / "logistics_pod"


@pytest.fixture(scope="module")
def pack():
    return pipeline.load_pack(PACK_DIR)


@pytest.fixture(scope="module")
def ref(pack):
    return pack.load_reference(PACK_DIR)


def good(**over):
    d = {"consignment_no": "KF-48201", "recipient_name": "T. Morrison", "delivered_at": "2026-11-12 10:42",
         "signature_present": True, "damage_noted": False, "damage_note": None, "packages_count": 4,
         "confidence": 0.95}
    d.update(over)
    return d


def check(pack, ref, data, today=date(2026, 11, 20)):
    return pack.checks("d.png", {**data, "_meta": {}}, {**ref, "_today": today})


def test_clean_docket_passes(pack, ref):
    assert check(pack, ref, good()) == []


@pytest.mark.parametrize("over, expected", [
    ({"consignment_no": "KF-99999"}, ["unknown_consignment"]),
    ({"consignment_no": None}, ["unknown_consignment"]),
    ({"consignment_no": " kf-48201 "}, []),                                           # tolerant of case and spaces
    ({"delivered_at": "2026-11-08 09:00"}, ["bad_date"]),                             # dispatched 9 Nov
    ({"delivered_at": "2026-11-09 07:00"}, []),                                       # same day as dispatch is fine
    ({"delivered_at": "2026-11-21 09:00"}, ["bad_date"]),                             # after DEMO_TODAY
    ({"delivered_at": "2026-11-20 09:00"}, []),                                       # today is fine
    ({"delivered_at": None}, ["bad_date"]),
    ({"delivered_at": "12/11/2026 10:42"}, ["bad_date"]),                             # not in the agreed format
    ({"signature_present": False}, ["no_signature"]),
    ({"damage_noted": True, "damage_note": "box crushed"}, ["damage"]),
    ({"packages_count": 3}, ["count_mismatch"]),
    ({"packages_count": None}, ["count_mismatch"]),
])
def test_each_check_fires(pack, ref, over, expected):
    assert check(pack, ref, good(**over)) == expected


def test_unknown_consignment_still_checks_the_date_against_today(pack, ref):
    assert check(pack, ref, good(consignment_no="KF-1", delivered_at="2026-12-01 09:00")) == [
        "unknown_consignment", "bad_date"]


def test_all_reasons_are_listed(pack, ref):
    data = good(signature_present=False, damage_noted=True, damage_note="wet", packages_count=1)
    assert check(pack, ref, data) == ["no_signature", "damage", "count_mismatch"]


def meta(route, *reasons):
    return {"_meta": {"route": route, "reasons": list(reasons)}}


def test_auto_item_gets_a_delivered_row_only(pack, ref):
    (row,) = pack.act("docket_01.png", {**good(), **meta("auto")}, ref, None)
    assert row["kind"] == "row" and row["sheet"] == "Delivered"
    assert row["values"]["Status"] == "POD OK" and row["values"]["Consignee"] == "Bellbird Hardware"


def test_damage_gets_a_fixed_claim_note_and_no_delivered_row(pack, ref):
    data = good(consignment_no="KF-48208", damage_noted=True, damage_note="2 cartons crushed, 1 wet", packages_count=7)
    (note,) = pack.act("docket_08.png", {**data, **meta("human", "damage")}, ref, None)
    assert note["folder"] == "work_orders" and note["name"] == "docket_08_damage_claim.txt"
    text = note["content"]
    assert text.startswith("DRAFT - NOT SENT\nDAMAGE CLAIM NOTE")
    assert "Brolga Electrical Wholesale, Rocklea" in text and "2 cartons crushed, 1 wet" in text
    assert "(shipment list: 7)" in text and "[STAFF TO CONFIRM" in text


def test_damage_with_an_unknown_consignment_still_gets_a_note_with_placeholders(pack, ref):
    data = good(consignment_no="KF-99999", damage_noted=True, damage_note=None)
    (note,) = pack.act("d.png", {**data, **meta("human", "unknown_consignment", "damage")}, ref, None)
    assert "[STAFF TO CONFIRM: consignee]" in note["content"] and "no note was readable" in note["content"]


def test_other_human_items_get_nothing(pack, ref):
    assert pack.act("d.png", {**good(signature_present=False), **meta("human", "no_signature")}, ref, None) == []


def test_end_to_end_with_a_mock_backend(pack, tmp_path):
    summary, res, backend, out = run_real_pack("logistics_pod", tmp_path)
    assert (summary["total"], summary["auto"], summary["human"]) == (10, 6, 4)
    assert res["docket_07.png"]["reasons"] == ["no_signature"]
    assert res["docket_08.png"]["reasons"] == ["damage"]
    assert res["docket_09.png"]["reasons"] == ["unknown_consignment"]
    assert res["docket_10.png"]["reasons"] == ["count_mismatch"]
    assert load_workbook(out / "report.xlsx")["Delivered"].max_row == 1 + 6
    assert [p.name for p in (out / "work_orders").iterdir()] == ["docket_08_damage_claim.txt"]
    assert all(c["image"] and c["image"][1] == "image/png" for c in backend.extract_calls())
    assert len(backend.extract_calls()) == 10 and backend.draft_calls() == []
