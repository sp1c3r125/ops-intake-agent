"""Everything the engine writes: log.jsonl, results.json, report.xlsx, dashboard.html, files, index.html.

Text from documents is untrusted. Every value that reaches HTML goes through esc(), and spreadsheet and CSV
cells are written so a value like `=HYPERLINK(...)` is never treated as a formula.
"""
from __future__ import annotations

import csv
import html
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

FILE_FOLDERS = ("drafts", "work_orders", "reminders")


# --------------------------------------------------------------------------- small helpers
def esc(value):
    """HTML-escape any value (None becomes empty)."""
    return html.escape("" if value is None else str(value), quote=True)


def safe_name(name):
    """A file name that cannot leave its folder or hide: no path parts, no leading dot, limited characters."""
    name = Path(str(name).replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    return name[:100] or "file"


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _plain(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return value


def csv_cell(value):
    """A CSV cell. Text that starts with = + - @ gets a leading quote so a spreadsheet will not run it."""
    value = _plain(value)
    if isinstance(value, (bool, int, float)):
        return value
    s = _CONTROL.sub("", str(value))
    return "'" + s if s.startswith(_FORMULA_START) else s


def prepare_out_dir(out_root, name):
    """Create a clean outputs/<name>/ (each run starts from scratch). Refuses to touch anything else."""
    out_root = Path(out_root).resolve()
    d = (out_root / name).resolve()
    if d.parent != out_root:
        raise ValueError(f"refusing to use {d} as an output folder")
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


# --------------------------------------------------------------------------- log.jsonl
class RunLog:
    """Appends one JSON line per step (SPEC core rule 9)."""

    def __init__(self, path, pack, backend):
        self.pack, self.backend = pack, backend
        self._f = Path(path).open("a", encoding="utf-8")

    def write(self, item, step, output=None, confidence=None, retried=False, first_error=None,
              raw_output=None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pack": self.pack, "item": item, "step": step, "output": output, "confidence": confidence,
            "backend": self.backend, "retried": bool(retried),
            "first_error": None if first_error is None else str(first_error)[:100],
        }
        if raw_output is not None:
            entry["raw_output"] = raw_output
        self._f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        self._f.flush()

    def close(self):
        self._f.close()


# --------------------------------------------------------------------------- results, files, csv
def write_results_json(out_dir, summary, results):
    (Path(out_dir) / "results.json").write_text(
        json.dumps({"summary": summary, "items": results}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")


def write_files(out_dir, files):
    """Write drafts/, work_orders/ and reminders/ files. Returns the relative paths written."""
    written = []
    for f in files:
        folder = Path(out_dir) / f["folder"]
        folder.mkdir(exist_ok=True)
        path = folder / safe_name(f["name"])
        path.write_text(f["content"], encoding="utf-8", newline="\n")
        written.append(f"{f['folder']}/{path.name}")
    return written


def write_csvs(out_dir, csvs):
    for name, rows in csvs.items():
        columns = list(dict.fromkeys(k for r in rows for k in r))
        with (Path(out_dir) / safe_name(name)).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columns)
            for r in rows:
                w.writerow([csv_cell(r.get(c)) for c in columns])


# --------------------------------------------------------------------------- report.xlsx
def _sheet_title(name):
    return re.sub(r"[\[\]:*?/\\]", "-", str(name))[:31] or "Sheet"


def _write_sheet(wb, title, columns, rows):
    ws = wb.create_sheet(_sheet_title(title))
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([_CONTROL.sub("", v) if isinstance(v, str) else v for v in (_plain(row.get(c)) for c in columns)])
    # Text must stay text: openpyxl would turn a string starting with "=" into a formula.
    for r in ws.iter_rows(min_row=2):
        for cell in r:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    for i, c in enumerate(columns, start=1):
        width = max([len(str(c))] + [len(str(_plain(r.get(c)))) for r in rows[:200]])
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(max(width + 2, 10), 60)
    ws.freeze_panes = "A2"


def write_report(path, results, sheets):
    """Items sheet (all fields, route, reasons), Exceptions sheet, then the pack's sheets."""
    wb = Workbook()
    wb.remove(wb.active)
    fields = list(dict.fromkeys(k for r in results if r["data"] for k in r["data"]))
    item_rows = [{"Item": r["item"], "Route": r["route"], "Reasons": ", ".join(r["reasons"]),
                  "Confidence": r["confidence"], **(r["data"] or {})} for r in results]
    _write_sheet(wb, "Items", ["Item", "Route", "Reasons", "Confidence"] + fields, item_rows)
    exc = [{"Item": r["item"], "Reasons": ", ".join(r["reasons"]), "Confidence": r["confidence"],
            "Summary": (r["data"] or {}).get("summary") if isinstance((r["data"] or {}).get("summary"), str) else "",
            "Detail": r.get("error") or ""} for r in results if r["route"] == "human"]
    _write_sheet(wb, "Exceptions", ["Item", "Reasons", "Confidence", "Summary", "Detail"], exc)
    for name, rows in sheets.items():
        if rows:
            _write_sheet(wb, name, list(dict.fromkeys(k for r in rows for k in r)), rows)
    wb.save(path)


# --------------------------------------------------------------------------- dashboard.html
_CSS = """
:root{--bg:#f7f7f5;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#deded8;--ok:#1f7a4d;--warn:#b3541e;--skip:#5a6270;--bar:#c9d6e8}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecece8;--mut:#9a9a94;--card:#202020;--line:#34342f;--ok:#58c08a;--warn:#f0905a;--skip:#9aa3b2;--bar:#33445e}}
*{box-sizing:border-box}body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:980px;margin:0 auto}h1{font-size:1.5rem;margin:0}h2{font-size:1.05rem;margin:28px 0 8px}
.mut{color:var(--mut);font-size:.9rem}.cards{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;min-width:130px}
.card b{display:block;font-size:1.6rem}.ok b{color:var(--ok)}.warn b{color:var(--warn)}.skip b{color:var(--skip)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
th{font-size:.8rem;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}
.bar{display:inline-block;height:10px;background:var(--bar);border-radius:3px;vertical-align:middle}
.wrap{overflow-x:auto}a{color:inherit}
"""


def _table(columns, rows):
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{esc(_plain(v))}</td>" for v in row) + "</tr>" for row in rows)
    if not rows:
        body = f'<tr><td colspan="{len(columns)}" class="mut">None</td></tr>'
    return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _reasons_table(reasons):
    """Reason, count, and a bar. Counts are ints from our own code; names are escaped."""
    if not reasons:
        return _table(["Reason", "Items"], [])
    top = max(reasons.values())
    rows = "".join(
        f'<tr><td>{esc(k)}</td><td>{esc(v)}</td>'
        f'<td><span class="bar" style="width:{max(4, round(160 * v / top))}px"></span></td></tr>'
        for k, v in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])))
    return ('<div class="wrap"><table><thead><tr><th>Reason</th><th>Items</th><th></th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def _page(title, inner):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f"<style>{_CSS}</style></head><body><main>{inner}</main></body></html>")


def render_dashboard(info, summary, results, extras):
    """info: {title, org, name}. extras: {name: rows} from the pack's EXTRA_SHEETS."""
    reasons = Counter()
    for r in results:
        reasons.update(r["reasons"])
    human =[r for r in results if r["route"] == "human"]
    parts = [
        f"<h1>{esc(info['title'])}</h1>",
        f'<div class="mut">{esc(info["org"])} &middot; backend: {esc(summary["backend"])} &middot; '
        f'demo date: {esc(summary["demo_today"])} &middot; {esc(summary["total"])} items</div>',
        '<div class="cards">'
        f'<div class="card ok"><b>{esc(summary["auto"])}</b>auto</div>'
        f'<div class="card warn"><b>{esc(summary["human"])}</b>needs a person</div>'
        f'<div class="card skip"><b>{esc(summary["skip"])}</b>skipped</div></div>',
        "<h2>Reasons</h2>",
        _reasons_table(reasons),
        "<h2>Needs a person</h2>",
        _table(["Item", "Reasons", "Summary", "Confidence"],
               [[r["item"], ", ".join(r["reasons"]),
                 (r["data"] or {}).get("summary") if isinstance((r["data"] or {}).get("summary"), str) else "",
                 r["confidence"]] for r in human]),
    ]
    for name, rows in extras.items():
        parts.append(f"<h2>{esc(name)}</h2>")
        cols = list(dict.fromkeys(k for r in rows for k in r))
        parts.append(_table(cols, [[r.get(c) for c in cols] for r in rows[:200]]))
    parts.append('<p class="mut">All data in this demo is fictional. Nothing is ever sent.</p>')
    return _page(info["title"], "".join(parts))


def write_dashboard(out_dir, info, summary, results, extras):
    (Path(out_dir) / "dashboard.html").write_text(render_dashboard(info, summary, results, extras),
                                                 encoding="utf-8")


# --------------------------------------------------------------------------- index.html (--all)
def top_reasons(summary, n=3):
    return sorted(summary["reasons"].items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def render_index(summaries):
    cards = []
    for s in summaries:
        top = ", ".join(f"{k} ({v})" for k, v in top_reasons(s)) or "none"
        cards.append(
            '<div class="card" style="flex:1 1 280px">'
            f'<h2 style="margin-top:0"><a href="{esc(s["name"])}/dashboard.html">{esc(s["title"])}</a></h2>'
            f'<div class="mut">{esc(s["org"])}</div>'
            f'<p>{esc(s["total"])} items &middot; {esc(s["auto"])} auto &middot; '
            f'{esc(s["human"])} needs a person</p>'
            f'<div class="mut">Top reasons: {esc(top)}</div></div>')
    inner = ("<h1>ops-intake-agent</h1>"
             '<div class="mut">One engine, industry packs. All data is fictional. Nothing is ever sent.</div>'
             f'<div class="cards">{"".join(cards)}</div>')
    return _page("ops-intake-agent", inner)


def write_index(out_root, summaries):
    path = Path(out_root) / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_index(summaries), encoding="utf-8")
    return path
