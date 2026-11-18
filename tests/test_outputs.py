"""Outputs: HTML escaping, spreadsheet/CSV formula safety, safe file names, clean output folders."""
import json
import zipfile

import pytest
from openpyxl import load_workbook

from engine import outputs

EVIL = '<script>alert("x")</script> & "quotes" <img src=x onerror=alert(1)>'


def result(item, route="human", reasons=("low_confidence",), data=None):
    data = {"summary": EVIL, "confidence": 0.5} if data is None else data
    return {"item": item, "route": route, "reasons": list(reasons), "confidence": data.get("confidence"),
            "data": data, "retried": False, "first_error": None, "error": None, "outputs": []}


SUMMARY = {"name": "p", "title": EVIL, "org": EVIL, "backend": EVIL, "demo_today": "2026-11-20",
           "total": 1, "auto": 0, "human": 1, "skip": 0, "reasons": {EVIL: 1}}


def test_dashboard_escapes_everything_from_documents():
    html = outputs.render_dashboard({"title": EVIL, "org": EVIL, "name": "p"}, SUMMARY,
                                    [result(EVIL, reasons=[EVIL])], {EVIL: [{EVIL: EVIL}]})
    assert "<script>" not in html and "<img" not in html and "onerror=alert(1)>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html and "&quot;" in html
    assert html.count("<script") == 0
    assert "http://" not in html and "https://" not in html          # nothing is loaded from outside


def test_dashboard_shows_counts_reasons_and_needs_human_list():
    res = [result("a.eml", reasons=["low_confidence", "unknown_property"], data={"summary": "Leaky tap", "confidence": 0.4}),
           result("b.eml", route="auto", reasons=[], data={"summary": "ok", "confidence": 0.9})]
    summary = {**SUMMARY, "title": "T", "org": "O", "backend": "mock", "total": 2, "auto": 1, "human": 1,
               "reasons": {"low_confidence": 1, "unknown_property": 1}}
    html = outputs.render_dashboard({"title": "T", "org": "O", "name": "p"}, summary, res, {"By kind": [{"Kind": "x", "Items": 1}]})
    for text in ("a.eml", "low_confidence, unknown_property", "Leaky tap", "By kind", "needs a person", "demo date: 2026-11-20"):
        assert text in html
    assert "b.eml" not in html                                        # an auto item is not on the needs-a-person list


def test_index_escapes_and_links_each_pack(tmp_path):
    s = {**SUMMARY, "name": "finance_receipts"}
    path = outputs.write_index(tmp_path / "outputs", [s])
    html = path.read_text(encoding="utf-8")
    assert "<script>" not in html and 'href="finance_receipts/dashboard.html"' in html
    assert "1 items" in html


def test_top_reasons_are_the_three_most_common():
    s = {"reasons": {"a": 1, "b": 5, "c": 3, "d": 3, "e": 2}}
    assert outputs.top_reasons(s) == [("b", 5), ("c", 3), ("d", 3)]


# --------------------------------------------------------------------------- spreadsheets and CSV
FORMULAS = ['=HYPERLINK("http://evil.example","click")', "+cmd|' /C calc'!A0", "-2+3", "@SUM(1,1)"]


def test_report_keeps_formula_looking_text_as_text(tmp_path):
    results = [result(f"i{n}", reasons=["low_confidence"], data={"summary": f, "confidence": 0.5})
               for n, f in enumerate(FORMULAS)]
    path = tmp_path / "report.xlsx"
    outputs.write_report(path, results, {"Extra": [{"Cell": f} for f in FORMULAS]})
    wb = load_workbook(path)
    for sheet, col in (("Items", "E"), ("Extra", "A")):
        values = [wb[sheet][f"{col}{r}"] for r in range(2, 2 + len(FORMULAS))]
        assert [c.value for c in values] == FORMULAS and all(c.data_type == "s" for c in values)
    with zipfile.ZipFile(path) as z:                                  # no formula element anywhere in the file
        assert not any(b"<f>" in z.read(n) for n in z.namelist() if n.startswith("xl/worksheets/"))


def test_report_sheets_and_columns(tmp_path):
    results = [result("a", data={"summary": "s", "confidence": 0.5, "items": [{"d": 1}]}),
               result("b", route="auto", reasons=[], data={"summary": "t", "confidence": 0.9, "items": []})]
    path = tmp_path / "r.xlsx"
    outputs.write_report(path, results, {"Approved": [{"Item": "b", "Total": 5}], "Empty": []})
    wb = load_workbook(path)
    assert wb.sheetnames == ["Items", "Exceptions", "Approved"]       # an empty extra sheet is not written
    header = [c.value for c in wb["Items"][1]]
    assert header[:4] == ["Item", "Route", "Reasons", "Confidence"] and "summary" in header
    assert wb["Items"]["C2"].value == "low_confidence"
    assert json.loads(wb["Items"].cell(row=2, column=header.index("items") + 1).value) == [{"d": 1}]
    assert [c.value for c in wb["Exceptions"][2]][:2] == ["a", "low_confidence"]


def test_a_control_character_does_not_break_the_workbook(tmp_path):
    outputs.write_report(tmp_path / "r.xlsx", [result("a", data={"summary": "bad\x00\x07text", "confidence": 0.5})], {})
    assert load_workbook(tmp_path / "r.xlsx")["Items"]["E2"].value == "badtext"


def test_csv_cells_cannot_run_as_formulas(tmp_path):
    outputs.write_csvs(tmp_path, {"export.csv": [{"Payee": f, "Amount": 5, "Tax": None} for f in FORMULAS]})
    lines = (tmp_path / "export.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Payee,Amount,Tax"
    assert all(line.startswith(("'=", "\"'=", "'+", "'-", "'@", "\"'+", "\"'-", "\"'@")) for line in lines[1:])
    assert outputs.csv_cell(-5) == -5 and outputs.csv_cell("Cafe") == "Cafe" and outputs.csv_cell(None) == ""


# --------------------------------------------------------------------------- files and folders
@pytest.mark.parametrize("name, expected", [
    ("../../etc/passwd", "passwd"), ("..\\..\\win.ini", "win.ini"), ("a b/c d.txt", "c_d.txt"),
    (".hidden", "hidden"), ("..", "file"), ("", "file"), ("report 01.eml.txt", "report_01.eml.txt"),
])
def test_safe_name(name, expected):
    assert outputs.safe_name(name) == expected


def test_files_cannot_escape_their_folder(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    written = outputs.write_files(out, [{"folder": "drafts", "name": "../../evil.txt", "content": "x"},
                                        {"folder": "reminders", "name": "r.ics", "content": "BEGIN:VCALENDAR"}])
    assert written == ["drafts/evil.txt", "reminders/r.ics"]
    assert (out / "drafts" / "evil.txt").exists() and not (tmp_path / "evil.txt").exists()


def test_prepare_out_dir_only_touches_its_own_folder(tmp_path):
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "f.txt").write_text("x")
    d = outputs.prepare_out_dir(tmp_path, "mypack")
    (d / "old.txt").write_text("old")
    assert (outputs.prepare_out_dir(tmp_path, "mypack") / "old.txt").exists() is False
    assert (keep / "f.txt").exists()
    for bad in ("..", "a/b", "../x", "."):
        with pytest.raises(ValueError):
            outputs.prepare_out_dir(tmp_path, bad)


def test_run_log_cuts_first_error_and_adds_raw_output_only_when_given(tmp_path):
    log = outputs.RunLog(tmp_path / "log.jsonl", "p", "mock")
    log.write("a", "extract", first_error="e" * 300)
    log.write("b", "extract", raw_output="{bad", retried=True)
    log.close()
    a, b = [json.loads(line) for line in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert len(a["first_error"]) == 100 and "raw_output" not in a
    assert b["raw_output"] == "{bad" and b["retried"] is True and b["first_error"] is None
