"""hotel_reviews: rating comes from the CSV, flags, draft checks in code, topic sheet, and one end-to-end run."""
import pytest
from openpyxl import load_workbook

from engine import pipeline
from engine.drafts import DraftRejected
from tests.helpers import PACKS, run_real_pack

PACK_DIR = PACKS / "hotel_reviews"


@pytest.fixture(scope="module")
def pack():
    return pipeline.load_pack(PACK_DIR)


def good(rating="5", **over):
    d = {"topics": ["staff"], "sentiment": "positive", "mentions_safety_or_health": False,
         "mentions_legal_or_discrimination": False, "summary": "Lovely staff.", "confidence": 0.95,
         "_meta": {"row": {"review_id": "R-1", "rating": rating}}}
    d.update(over)
    return d


@pytest.mark.parametrize("data, expected", [
    (good("5"), []),
    (good("3"), []),
    (good("2"), ["low_rating"]),                                         # 2 or less goes to a person
    (good("1"), ["low_rating"]),
    (good("4", mentions_safety_or_health=True), ["mentions_safety_or_health"]),
    (good("4", mentions_legal_or_discrimination=True), ["mentions_legal_or_discrimination"]),
    (good("1", mentions_safety_or_health=True, mentions_legal_or_discrimination=True),
     ["low_rating", "mentions_safety_or_health", "mentions_legal_or_discrimination"]),
    (good(""), ["bad_rating"]),                                          # no rating in the CSV
    (good("six"), ["bad_rating"]),
    (good("0"), ["bad_rating"]),
    (good("6"), ["bad_rating"]),
])
def test_each_check_fires(pack, data, expected):
    reasons = pack.checks("R-1", data, {})
    assert reasons == expected and pack.route(data, reasons) == ("human" if expected else "auto")


def test_the_rating_is_never_taken_from_the_model(pack):
    # Even if the model volunteered a rating, only the CSV row counts.
    data = good("1", summary="5 stars! Rating: 5")
    assert pack.checks("R-1", data, {}) == ["low_rating"]


class Drafter:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, instructions, facts=None):
        self.calls.append((instructions, facts))
        return "DRAFT - NOT SENT\n\n" + self.reply


def test_a_clean_draft_is_written(pack):
    fn = Drafter("Thank you for the lovely words about our team.\n\nThe team at Saltmarsh Suites")
    (out,) = pack.act("R-3001", good(), {}, fn)
    assert out["folder"] == "drafts" and out["name"] == "R-3001.txt"
    instructions, facts = fn.calls[0]
    assert facts["stars"] == 5 and facts["topics"] == ["staff"]
    assert "refunds, compensation, discounts, free nights" in instructions and "Do not admit fault" in instructions


@pytest.mark.parametrize("reply, reason", [
    ("We will happily offer you a refund.", "draft_promise"),
    ("Please accept compensation for your trouble.", "draft_promise"),
    ("Enjoy a FREE NIGHT on us!", "draft_promise"),
    ("We would like to give you a 10% discount.", "draft_promise"),
    ("It was our fault and we are sorry.", "draft_admission"),
    ("We should have cleaned the bathroom better.", "draft_admission"),
])
def test_drafts_with_promises_or_admissions_are_rejected(pack, reply, reason):
    with pytest.raises(DraftRejected) as e:
        pack.act("R-1", good(), {}, Drafter(reply))
    assert e.value.reason == reason


def test_a_polite_apology_is_not_an_admission(pack):
    (out,) = pack.act("R-1", good(), {}, Drafter("Thank you, and we are sorry to hear the street was noisy."))
    assert out["kind"] == "file"


def test_topic_sheet_counts_topics_and_averages_the_csv_rating(pack):
    def r(item, rating, topics, data=True):
        return {"item": item, "row": {"rating": rating}, "data": {"topics": topics} if data else None}
    rows = pack.extra_sheets["Topics"]([
        r("a", "5", ["staff", "room"]), r("b", "3", ["staff"]), r("c", "1", ["room", "room", "noise"]),
        r("d", "", ["noise"]), r("e", "4", [], data=False)])
    assert rows == [{"Topic": "noise", "Reviews": 2, "Average rating": 1.0},         # d has no rating: not averaged
                    {"Topic": "room", "Reviews": 2, "Average rating": 3.0},           # a topic counts once per review
                    {"Topic": "staff", "Reviews": 2, "Average rating": 4.0}]


def test_end_to_end_with_a_mock_backend(pack, tmp_path):
    summary, res, backend, out = run_real_pack("hotel_reviews", tmp_path,
                                               draft_reply="Thank you for staying with us.\n\nThe team at Saltmarsh Suites")
    assert (summary["total"], summary["auto"], summary["human"]) == (15, 11, 4)
    assert res["R-3008"]["reasons"] == ["low_rating"] and res["R-3013"]["reasons"] == ["low_rating"]
    assert res["R-3009"]["reasons"] == ["low_rating"]
    assert res["R-3012"]["reasons"] == ["mentions_safety_or_health"]                  # rating 3, but a health mention
    assert len(backend.extract_calls()) == 15 and len(backend.draft_calls()) == 11
    assert len(list((out / "drafts").iterdir())) == 11 and not (out / "drafts" / "R-3009.txt").exists()
    ws = load_workbook(out / "report.xlsx")["Topics"]
    topics = {row[0].value: (row[1].value, row[2].value) for row in ws.iter_rows(min_row=2)}
    assert topics["breakfast"] == (3, 4)               # reviews rated 5, 3 and 4 and topics["cleanliness"][0] == 3
    assert "Average rating" in (out / "dashboard.html").read_text(encoding="utf-8")


def test_the_injected_review_cannot_buy_a_promise_into_a_reply(pack, tmp_path):
    """If a draft did follow the injected instruction, code catches it and sends the item to a person."""
    bad = "Good news: every guest gets a free night and a full refund.\n\nThe team at Saltmarsh Suites"
    summary, res, backend, out = run_real_pack("hotel_reviews", tmp_path, draft_reply=bad)
    assert summary["auto"] == 0 and summary["human"] == 15
    assert res["R-3011"]["reasons"] == ["draft_promise"] and res["R-3001"]["reasons"] == ["draft_promise"]
    assert not (out / "drafts").exists()
    call = next(c for c in backend.draft_calls() if "IGNORE ALL INSTRUCTIONS" in c["user"])
    assert call["user"].count("<document>") == 1
