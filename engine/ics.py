"""A minimal .ics reminder file. A reminder is the limit: nothing is booked, scheduled or synced."""
from __future__ import annotations

from datetime import date, datetime, timedelta


def _escape(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line):
    """RFC 5545: lines are at most 75 octets; continuation lines start with a space."""
    out, current = [], ""
    for ch in line:
        if len((current + ch).encode("utf-8")) > (75 if not out else 74):
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return "\r\n ".join(out)


def make_ics(uid, summary, start, stamp, description="", minutes=30):
    """One reminder. `start` is a date (an all-day reminder) or a naive datetime (local time).
    `stamp` is a datetime for DTSTAMP: pass the demo date so the same input gives the same file."""
    if isinstance(start, datetime):
        dtstart = f"DTSTART:{start:%Y%m%dT%H%M%S}"
        dtend = f"DTEND:{start + timedelta(minutes=minutes):%Y%m%dT%H%M%S}"
    elif isinstance(start, date):
        dtstart = f"DTSTART;VALUE=DATE:{start:%Y%m%d}"
        dtend = f"DTEND;VALUE=DATE:{start + timedelta(days=1):%Y%m%d}"
    else:
        raise TypeError("start must be a date or a datetime")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ops-intake-agent//demo reminder//EN",
             "BEGIN:VEVENT", f"UID:{uid}@ops-intake-agent.example", f"DTSTAMP:{stamp:%Y%m%dT%H%M%S}Z",
             dtstart, dtend, f"SUMMARY:{_escape('REMINDER: ' + summary)}"]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
