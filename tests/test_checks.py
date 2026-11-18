from datetime import date

import pytest

from engine import checks as ck

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["a", "b"]},
        "n": {"type": "integer", "minimum": 0, "maximum": 10},
        "x": {"type": ["number", "null"]},
        "flag": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "d": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
    },
    "required": ["kind"],
    "additionalProperties": False,
}


@pytest.mark.parametrize("value", [
    {"kind": "a"}, {"kind": "b", "n": 3, "x": None, "flag": False, "tags": ["t"], "d": "2026-11-20"},
    {"kind": "a", "n": 3.0}, {"kind": "a", "x": 1}, {"kind": "a", "x": 1.5},
])
def test_valid(value):
    assert ck.validate_json(value, SCHEMA) == []


@pytest.mark.parametrize("value, fragment", [
    ({}, "missing required field 'kind'"),
    ({"kind": "c"}, "not one of"),
    ({"kind": "a", "n": 11}, "above 10"),
    ({"kind": "a", "n": -1}, "below 0"),
    ({"kind": "a", "n": 1.5}, "expected integer"),
    ({"kind": "a", "n": True}, "expected integer"),            # bool is not a number
    ({"kind": "a", "x": "5"}, "expected number|null"),
    ({"kind": "a", "flag": 1}, "expected boolean"),
    ({"kind": "a", "tags": ["ok", 2]}, "tags[1]"),
    ({"kind": "a", "d": "20/11/2026"}, "does not match"),
    ({"kind": "a", "extra": 1}, "unexpected field 'extra'"),
    ("text", "expected object"),
])
def test_invalid(value, fragment):
    errors = ck.validate_json(value, SCHEMA)
    assert errors and any(fragment in e for e in errors), errors


def test_bool_does_not_match_a_numeric_enum():
    assert ck.validate_json(True, {"enum": [1]})


# --------------------------------------------------------------------------- money
@pytest.mark.parametrize("parts, total, ok", [
    ([100, 10], 110, True), ([100.0, 10.0], 110.02, True), ([100, 10], 110.03, False),   # 0.02 allowed, 0.03 not
    (["100.00", "10.00"], "110.00", True), ([0.1, 0.2], 0.3, True),                      # no float drift
    ([100, None], 110, False), ([100, "ten"], 110, False), ([True, 1], 2, False),
])
def test_money_sum(parts, total, ok):
    assert ck.money_sum_ok(parts, total) is ok


def test_money_close_tolerance_is_inclusive_and_configurable():
    assert ck.money_close(10.00, 10.05, tol="0.05") and not ck.money_close(10.00, 10.06, tol="0.05")
    assert not ck.money_close(None, 1) and not ck.money_close(float("nan"), 1)


# --------------------------------------------------------------------------- dates
def test_parse_date_is_strict():
    assert ck.parse_date("2026-11-20") == date(2026, 11, 20)
    for bad in ("20/11/2026", "2026-13-01", "2026-11-20 10:00", None, 5, ""):
        assert ck.parse_date(bad) is None


def test_parse_datetime():
    assert ck.parse_datetime("2026-11-20 14:30").hour == 14
    assert ck.parse_datetime("2026-11-20T14:30:05").second == 5
    assert ck.parse_datetime("2026-11-20") is None and ck.parse_datetime("nope") is None


def test_date_order():
    assert ck.date_order_ok("2026-11-01", "2026-11-30")
    assert ck.date_order_ok("2026-11-01", "2026-11-01") and not ck.date_order_ok("2026-11-01", "2026-11-01", strict=True)
    assert not ck.date_order_ok("2026-11-30", "2026-11-01")
    assert not ck.date_order_ok("garbage", "2026-11-01")       # unreadable -> False, so the caller flags it
    assert ck.date_order_ok(date(2026, 1, 1), "2026-02-01")


# --------------------------------------------------------------------------- duplicates and lookups
def test_duplicate_ignores_case_spacing_and_money_format():
    ref = {}
    assert ck.is_duplicate(ref, "Acme  Parts", 110) is False
    assert ck.is_duplicate(ref, "acme parts", "110.00") is True
    assert ck.is_duplicate(ref, "acme parts", 111) is False
    assert ck.is_duplicate({}, "acme", 1) is False                  # a fresh ref has no memory


def test_csv_lookup(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("﻿consignment_no,packages\nKF-001,3\n kf-002 , 4 \n", encoding="utf-8")
    table = ck.index_csv(p, "consignment_no")
    assert ck.lookup(table, "KF-001")["packages"] == "3"
    assert ck.lookup(table, " kf-001 ")["packages"] == "3"
    assert ck.lookup(table, "KF-002")["packages"] == "4"
    assert ck.lookup(table, "KF-999") is None and ck.lookup(table, None) is None and ck.lookup(table, "") is None
    assert [r["packages"] for r in ck.read_csv(p)] == ["3", "4"]


# --------------------------------------------------------------------------- business days and reminders
def test_business_days_between():
    fri = date(2026, 11, 20)                                       # DEMO_TODAY is a Friday
    assert ck.business_days_between(fri, date(2026, 11, 21)) == 0   # Saturday
    assert ck.business_days_between(fri, date(2026, 11, 23)) == 1   # Monday
    assert ck.business_days_between(fri, date(2026, 11, 24)) == 2
    assert ck.business_days_between(fri, date(2026, 11, 25)) == 3
    assert ck.business_days_between(fri, fri) == 0 and ck.business_days_between(fri, date(2026, 11, 1)) == 0


def test_add_business_days():
    assert ck.add_business_days(date(2026, 12, 4), -2) == date(2026, 12, 2)    # Friday -> Wednesday
    assert ck.add_business_days(date(2026, 12, 7), -2) == date(2026, 12, 3)    # Monday skips the weekend
    assert ck.add_business_days(date(2026, 11, 20), 1) == date(2026, 11, 23)
    assert ck.add_business_days(date(2026, 11, 20), 0) == date(2026, 11, 20)


def test_ics_all_day_and_timed():
    from datetime import datetime
    from engine.ics import make_ics
    stamp = datetime(2026, 11, 20)
    day = make_ics("u1", "Renew, the lease; now", date(2026, 12, 25), stamp, description="Line1\nLine2")
    assert day.startswith("BEGIN:VCALENDAR\r\n") and day.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261225" in day and "DTEND;VALUE=DATE:20261226" in day
    assert r"SUMMARY:REMINDER: Renew\, the lease\; now" in day and r"DESCRIPTION:Line1\nLine2" in day
    assert "DTSTAMP:20261120T000000Z" in day and "UID:u1@ops-intake-agent.example" in day
    timed = make_ics("u2", "Closing", datetime(2026, 12, 4, 14, 0), stamp, minutes=15)
    assert "DTSTART:20261204T140000" in timed and "DTEND:20261204T141500" in timed
    long = make_ics("u3", "x" * 200, date(2026, 12, 1), stamp)
    assert all(len(line.encode()) <= 75 for line in long.split("\r\n"))
    with pytest.raises(TypeError):
        make_ics("u4", "x", "2026-12-01", stamp)
