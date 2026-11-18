"""Shared, deterministic helpers for pack checks: JSON validation, money sums, dates, duplicates, lookups.

The LLM extracts; code verifies (SPEC core rule 6). Everything here is plain code with no model calls.
"""
from __future__ import annotations

import csv
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

# --------------------------------------------------------------------------- JSON validation
# A small validator for the JSON-schema subset the packs use. Code validates the model's output again
# even when the backend enforced the schema (SPEC core rule 2). It never repairs anything.


def _is_type(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and value.is_integer())
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    return False


def _same(a, b):
    return a == b and isinstance(a, bool) == isinstance(b, bool)


def validate_json(value, schema, path="$"):
    """Return a list of error strings (empty if valid). Supports type, enum, required, properties,
    additionalProperties=false, items, minimum, maximum, minLength, maxLength, minItems, pattern."""
    errors = []
    t = schema.get("type")
    if t is not None:
        names = t if isinstance(t, list) else [t]
        if not any(_is_type(value, n) for n in names):
            return [f"{path}: expected {'|'.join(names)}, got {type(value).__name__}"]
    if "enum" in schema and not any(_same(value, e) for e in schema["enum"]):
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} is above {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field {key!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected field {key!r}")
        for key, sub in props.items():
            if key in value:
                errors += validate_json(value[key], sub, f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, v in enumerate(value):
                errors += validate_json(v, schema["items"], f"{path}[{i}]")
    return errors


# --------------------------------------------------------------------------- money
def to_decimal(x):
    """Decimal for a number or numeric string; None for anything else (including bool and None)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        d = Decimal(str(x).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def money_close(a, b, tol="0.02"):
    """True if a and b are within tol of each other (inclusive). False if either is not a number."""
    da, db = to_decimal(a), to_decimal(b)
    if da is None or db is None:
        return False
    return abs(da - db) <= Decimal(str(tol))


def money_sum_ok(parts, total, tol="0.02"):
    """True if the parts add up to total within tol. False if any value is missing or not a number."""
    decimals = [to_decimal(p) for p in parts]
    if any(d is None for d in decimals):
        return False
    return money_close(sum(decimals, Decimal(0)), total, tol)


# --------------------------------------------------------------------------- dates
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$")


def parse_date(s):
    """A strict YYYY-MM-DD string -> date, else None."""
    if not isinstance(s, str) or not _DATE.match(s.strip()):
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


def parse_datetime(s):
    """'YYYY-MM-DD HH:MM' (or with T, or with seconds) -> naive datetime, else None."""
    if not isinstance(s, str) or not _DATETIME.match(s.strip()):
        return None
    try:
        return datetime.fromisoformat(s.strip().replace(" ", "T"))
    except ValueError:
        return None


def date_order_ok(earlier, later, strict=False):
    """True if `earlier` is on or before `later` (strictly before if strict). Both are YYYY-MM-DD strings
    or dates. If either cannot be read, returns False so the caller flags it."""
    a = earlier if isinstance(earlier, date) else parse_date(earlier)
    b = later if isinstance(later, date) else parse_date(later)
    if a is None or b is None:
        return False
    return a < b if strict else a <= b


def business_days_between(start, end):
    """Weekdays (Mon to Fri) in the range after `start` up to and including `end`. 0 if end is not after
    start. Public holidays are not known to this function."""
    if end <= start:
        return 0
    days = (end - start).days
    return sum(1 for n in range(1, days + 1) if (start + timedelta(days=n)).weekday() < 5)


def add_business_days(day, n):
    """The date n business days before (n negative) or after (n positive) `day`."""
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        day += timedelta(days=step)
        if day.weekday() < 5:
            remaining -= 1
    return day


# --------------------------------------------------------------------------- duplicates
def _norm(part):
    if isinstance(part, str):
        d = to_decimal(part)
        return d.normalize() if d is not None else " ".join(part.casefold().split())
    d = to_decimal(part)
    return d.normalize() if d is not None else part


def is_duplicate(ref, *parts):
    """True if the same key was seen earlier in this run. Records the key. The engine puts a fresh set in
    ref["_seen"] at the start of each run and processes items in a fixed order, so the later item is the
    duplicate. Keys are compared ignoring case and spacing, and money by value (10.5 equals "10.50")."""
    seen = ref.setdefault("_seen", set())
    key = tuple(_norm(p) for p in parts)
    if key in seen:
        return True
    seen.add(key)
    return False


# --------------------------------------------------------------------------- reference CSVs
def read_csv(path):
    """Rows of a CSV as dicts (UTF-8, BOM tolerated). Values are stripped."""
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _key(value):
    return " ".join(str(value).casefold().split())


def index_csv(path, key):
    """A CSV as {normalised key value: row}. If a key repeats, the first row wins."""
    table = {}
    for row in read_csv(path):
        table.setdefault(_key(row[key]), row)
    return table


def lookup(table, key):
    """The row for `key` from an index_csv table, or None. A missing or empty key gives None."""
    if key is None or str(key).strip() == "":
        return None
    return table.get(_key(key))
