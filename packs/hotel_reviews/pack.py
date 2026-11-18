"""hotel_reviews: guest reviews (rows of a CSV) -> topics, flags and reply drafts. Never posts anything.

The star rating comes from the CSV row, never from Claude. Code checks every draft for promises and admissions.
"""
from pathlib import Path

NAME = "hotel_reviews"
TITLE = "Review replies"
ORG = "Saltmarsh Suites (fictional)"
INPUT_GLOB = "reference/reviews.csv"
INPUT_KIND = "csv_rows"
DRAFTS = True

PROMISES = ("refund", "compensat", "free night", "discount")                  # SPEC: draft_promise
ADMISSIONS = ("our fault", "our mistake", "our error", "we were wrong", "we got it wrong", "we failed",
              "we should have", "we admit", "take full responsibility")      # drafts never admit fault

INSTRUCTIONS = (
    "Write a short, warm public reply to a guest review of the hotel, as the hotel's team. Thank the guest and "
    "mention one specific thing they said. Do not offer or hint at refunds, compensation, discounts, free nights, "
    "upgrades or any other benefit. Do not admit fault, blame anyone, or make promises about what the hotel will "
    "do. Do not quote the guest's rating. Sign off 'The team at Saltmarsh Suites'.")


def rating_of(row):
    """The 1 to 5 star rating from the CSV row, or None if it is missing or not a whole number from 1 to 5."""
    try:
        n = int(str((row or {}).get("rating", "")).strip())
    except ValueError:
        return None
    return n if 1 <= n <= 5 else None


def load_reference(pack_dir):
    return {}


def checks(item_id, data, ref):
    reasons = []
    rating = rating_of(data["_meta"]["row"])
    if rating is None:
        reasons.append("bad_rating")
    elif rating <= 2:
        reasons.append("low_rating")
    if data["mentions_safety_or_health"]:
        reasons.append("mentions_safety_or_health")
    if data["mentions_legal_or_discrimination"]:
        reasons.append("mentions_legal_or_discrimination")
    return reasons


def route(data, reasons):
    return "human" if reasons else "auto"


def draft_problem(text):
    """The reason a draft must go to a person, or None."""
    low = text.casefold()
    if any(p in low for p in PROMISES):
        return "draft_promise"
    if any(a in low for a in ADMISSIONS):
        return "draft_admission"
    return None


def act(item_id, data, ref, draft_fn):
    from engine.drafts import DraftRejected
    text = draft_fn(INSTRUCTIONS, {"stars": rating_of(data["_meta"]["row"]), "topics": data["topics"],
                                   "sentiment": data["sentiment"], "review_summary": data["summary"]})
    problem = draft_problem(text)
    if problem:
        raise DraftRejected(problem)
    return [{"kind": "file", "folder": "drafts", "name": f"{Path(str(item_id)).stem}.txt", "content": text}]


def topic_stats(results):
    """Topic counts and the average star rating per topic (the rating comes from the CSV rows)."""
    stats = {}
    for r in results:
        if not r["data"]:
            continue
        rating = rating_of(r.get("row"))
        for topic in set(r["data"]["topics"]):
            s = stats.setdefault(topic, {"n": 0, "sum": 0, "rated": 0})
            s["n"] += 1
            if rating is not None:
                s["sum"] += rating
                s["rated"] += 1
    return [{"Topic": t, "Reviews": s["n"], "Average rating": round(s["sum"] / s["rated"], 2) if s["rated"] else None}
            for t, s in sorted(stats.items(), key=lambda kv: (-kv[1]["n"], kv[0]))]


EXTRA_SHEETS = {"Topics": topic_stats}
