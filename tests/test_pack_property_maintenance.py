"""property_maintenance: checks, routing, safety reply, work orders, and one end-to-end run."""
import pytest

from engine import pipeline
from tests.helpers import PACKS, run_real_pack

PACK_DIR = PACKS / "property_maintenance"


@pytest.fixture(scope="module")
def pack():
    return pipeline.load_pack(PACK_DIR)


@pytest.fixture(scope="module")
def ref(pack):
    return pack.load_reference(PACK_DIR)


def good(**over):
    d = {"issue_type": "plumbing", "urgency": "routine", "hazard": "none",
         "property_hint": "9 Plover Street, Brunswick", "access_notes": None, "summary": "Tap drips.",
         "needs_more_info": False, "confidence": 0.95}
    d.update(over)
    return d


def check(pack, ref, data):
    return pack.checks("x.eml", {**data, "_meta": {}}, ref)


def test_clean_request_passes(pack, ref):
    assert check(pack, ref, good()) == []


@pytest.mark.parametrize("over, expected", [
    ({"hazard": "gas_smell"}, ["safety"]),
    ({"hazard": "electrical_hazard"}, ["safety"]),
    ({"hazard": "flooding"}, ["safety"]),
    ({"urgency": "urgent"}, ["urgent"]),
    ({"hazard": "gas_smell", "urgency": "urgent"}, ["safety", "urgent"]),
    ({"property_hint": None}, ["unknown_property"]),
    ({"property_hint": "1 Nowhere Lane, Elsewhere"}, ["unknown_property"]),
    ({"property_hint": "Northcote"}, ["unknown_property"]),           # two properties match: too vague
    ({"property_hint": "Plover Street"}, []),                         # one property matches: fine
    ({"issue_type": "other"}, ["category_other"]),
    ({"needs_more_info": True}, ["needs_more_info"]),
    ({"issue_type": "other", "property_hint": None, "needs_more_info": True},
     ["unknown_property", "category_other", "needs_more_info"]),
])
def test_each_check_fires(pack, ref, over, expected):
    assert check(pack, ref, good(**over)) == expected


def test_property_lookup_by_id_address_or_part_of_address(pack, ref):
    def find(pack_, ref_, hint):
        return pack_.checks.__globals__["find_property"](hint, ref_["properties"])
    assert find(pack, ref, "P-1003")["tenant"] == "Ayesha Khan"
    assert find(pack, ref, "unit 4, 18 wattlebird lane")["property_id"] == "P-1001"
    assert find(pack, ref, "I live at 27 Banksia Court, Thornbury VIC 3071 now")["property_id"] == "P-1002"
    assert find(pack, ref, "Magpie Road")["property_id"] == "P-1010"
    assert find(pack, ref, "Northcote") is None                          # two properties: ambiguous, so unknown
    assert find(pack, ref, "") is None and find(pack, ref, None) is None and find(pack, ref, "abc") is None


def test_route_is_human_for_any_reason(pack):
    assert pack.route(good(), []) == "auto"
    assert pack.route(good(), ["urgent"]) == "human"


def meta(*reasons):
    return {"_meta": {"reasons": list(reasons), "route": "human" if reasons else "auto"}}


def test_routine_work_order_goes_to_the_right_trade(pack, ref):
    (out,) = pack.act("02_ac_not_cooling.eml", {**good(issue_type="hvac", property_hint="27 Banksia Court, Thornbury",
                                                       access_notes="Weekdays after 10am"), **meta()}, ref, None)
    assert out["folder"] == "work_orders" and out["name"] == "02_ac_not_cooling.txt"
    text = out["content"]
    assert text.startswith("DRAFT - NOT SENT\nWORK ORDER")
    assert "Westgate Climate Services (fictional) <estimating@westgateclimate.example>" in text
    assert "27 Banksia Court, Thornbury VIC 3071 (P-1002)" in text and "Tomas Varga" in text
    assert "Weekdays after 10am" in text and "$800" in text


def test_urgent_work_order_is_labelled_and_missing_access_is_a_placeholder(pack, ref):
    (out,) = pack.act("05.eml", {**good(urgency="urgent", property_hint="P-1005"), **meta("urgent")}, ref, None)
    assert out["content"].startswith("DRAFT - NOT SENT\nURGENT WORK ORDER")
    assert "[STAFF TO CONFIRM: access arrangements]" in out["content"]


@pytest.mark.parametrize("reasons", [["unknown_property"], ["category_other", "needs_more_info"], ["urgent", "low_confidence"]])
def test_no_work_order_when_something_else_is_wrong(pack, ref, reasons):
    assert pack.act("x.eml", {**good(), **meta(*reasons)}, ref, None) == []


@pytest.mark.parametrize("hazard, fragment", [("gas_smell", "Do not use light switches"),
                                              ("electrical_hazard", "turn off the power at the switchboard"),
                                              ("flooding", "turn off the water at the mains")])
def test_hazard_gets_the_fixed_safety_reply_and_no_work_order(pack, ref, hazard, fragment):
    rows = pack.act("01_gas_smell.eml", {**good(hazard=hazard, property_hint="P-1001", urgency="urgent"),
                                         **meta("safety", "urgent")}, ref, None)
    assert len(rows) == 1 and rows[0]["folder"] == "drafts" and rows[0]["name"] == "01_gas_smell_safety_reply.txt"
    text = rows[0]["content"]
    assert text.startswith("DRAFT - NOT SENT") and fragment in text
    assert "[EMERGENCY NUMBER]" in text and "Hannah Brooke" in text and "[STAFF TO CONFIRM" in text


def test_safety_reply_still_written_when_the_property_is_unknown(pack, ref):
    (row,) = pack.act("x.eml", {**good(hazard="gas_smell", property_hint=None), **meta("safety", "unknown_property")},
                      ref, None)
    assert "[TENANT NAME]" in row["content"]


def test_work_order_for_a_trade_we_do_not_have_fails_safe(pack, ref):
    reference = {**ref, "trades": {}}
    with pytest.raises(ValueError):
        pack.act("x.eml", {**good(), **meta()}, reference, None)         # engine turns this into act_failed


def test_end_to_end_with_a_mock_backend(pack, tmp_path):
    summary, res, backend, out = run_real_pack("property_maintenance", tmp_path)
    assert (summary["total"], summary["auto"], summary["human"]) == (12, 7, 5)
    assert res["01_gas_smell.eml"]["reasons"] == ["safety", "urgent"]
    assert res["04_sparking_power_point.eml"]["reasons"] == ["safety", "urgent"]
    assert res["05_no_hot_water.eml"]["reasons"] == ["urgent"]
    assert res["11_vague_1.eml"]["reasons"] == ["unknown_property", "category_other", "needs_more_info", "low_confidence"]
    assert res["12_vague_2.eml"]["reasons"] == ["unknown_property", "category_other", "needs_more_info", "low_confidence"]
    assert all(res[k]["route"] == "auto" for k in ("02_ac_not_cooling.eml", "03_leaking_tap.eml", "06_dishwasher.eml",
                                                   "07_mice.eml", "08_front_door_lock.eml", "09_ceiling_stain.eml",
                                                   "10_injection.eml"))
    # The injected email is read as an ordinary fan problem. It is not made urgent and the limit is the property's own.
    inj = (out / "work_orders" / "10_injection.txt").read_text(encoding="utf-8")
    assert "$500" in inj and "URGENT" not in inj and "harvest.example" not in inj
    # 8 work orders (7 routine + 1 urgent), 2 safety replies, and nothing for the vague emails.
    assert sorted(p.name for p in (out / "work_orders").iterdir()) == sorted(
        f"{n}.txt" for n in ("02_ac_not_cooling", "03_leaking_tap", "05_no_hot_water", "06_dishwasher", "07_mice",
                             "08_front_door_lock", "09_ceiling_stain", "10_injection"))
    assert sorted(p.name for p in (out / "drafts").iterdir()) == ["01_gas_smell_safety_reply.txt",
                                                                    "04_sparking_power_point_safety_reply.txt"]
    assert "URGENT WORK ORDER" in (out / "work_orders" / "05_no_hot_water.txt").read_text(encoding="utf-8")
    assert "estimating@westgateclimate.example" in (out / "work_orders" / "02_ac_not_cooling.txt").read_text(encoding="utf-8")
    # No Claude draft calls: the templates are filled by code.
    assert len(backend.extract_calls()) == 12 and backend.draft_calls() == []
