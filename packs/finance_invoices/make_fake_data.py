"""Generate the fake supplier invoices for finance_invoices. Run:  python packs/finance_invoices/make_fake_data.py

10 PDF invoices with a text layer, made with fpdf2 in three layouts (6 clean, 1 with no PO, 1 over its PO, 1
duplicate, 1 with a wrong line sum), the PO register, and the canned model answers used by the tests.
All suppliers are fictional and the ABNs are obviously fake.
"""
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import fakegen as fg  # noqa: E402

D = Decimal
SUPPLIERS = {
    "banksia": ("Banksia Office Supplies Pty Ltd", "00 000 000 011", "14 Example Road, Moorabbin VIC 3189"),
    "kookaburra": ("Kookaburra Cleaning Services Pty Ltd", "00 000 000 022", "3 Sample Court, Clayton VIC 3168"),
    "lyrebird": ("Lyrebird IT Support Pty Ltd", "00 000 000 033", "Level 2, 77 Demo Street, Richmond VIC 3121"),
    "plover": ("Plover Courier Co Pty Ltd", "00 000 000 044", "5 Freight Lane, Tullamarine VIC 3043"),
    "wattle": ("Wattle Print and Signs Pty Ltd", "00 000 000 055", "21 Inkwell Road, Collingwood VIC 3066"),
    "saltbush": ("Saltbush Catering Pty Ltd", "00 000 000 066", "8 Pantry Place, Footscray VIC 3011"),
    "heron": ("Heron Furniture Hire Pty Ltd", "00 000 000 077", "60 Warehouse Way, Dandenong VIC 3175"),
}

PO_REGISTER = [  # po_number, supplier, amount, status
    ("PO-7001", SUPPLIERS["banksia"][0], "1200.00", "open"),
    ("PO-7002", SUPPLIERS["kookaburra"][0], "2400.00", "open"),
    ("PO-7003", SUPPLIERS["lyrebird"][0], "5500.00", "open"),
    ("PO-7004", SUPPLIERS["plover"][0], "800.00", "open"),
    ("PO-7005", SUPPLIERS["wattle"][0], "950.00", "open"),
    ("PO-7006", SUPPLIERS["saltbush"][0], "1800.00", "open"),
    ("PO-7007", SUPPLIERS["heron"][0], "6000.00", "open"),
    ("PO-7008", SUPPLIERS["banksia"][0], "400.00", "closed"),
]


def inv(file, key, number, issued, due, po, lines, layout, printed_subtotal=None):
    lines = [(d, D(str(q)), D(str(p))) for d, q, p in lines]
    subtotal = sum(q * p for _, q, p in lines)
    printed = D(str(printed_subtotal)) if printed_subtotal is not None else subtotal
    tax = (printed * D("0.1")).quantize(D("0.01"))
    return {"file": file, "supplier": SUPPLIERS[key], "number": number, "issued": issued, "due": due, "po": po,
            "lines": lines, "subtotal": printed, "tax": tax, "total": printed + tax, "layout": layout}


INVOICES = [
    inv("invoice_01.pdf", "banksia", "INV-2201", date(2026, 10, 30), date(2026, 11, 29), "PO-7001",
        [("A4 copy paper (carton)", 20, "12.50"), ("Laser toner cartridge", 4, "85.00")], "A"),
    inv("invoice_02.pdf", "kookaburra", "INV-0457", date(2026, 11, 2), date(2026, 12, 2), "PO-7002",
        [("Office cleaning, October 2026", 1, "1800.00")], "B"),
    inv("invoice_03.pdf", "lyrebird", "INV-9034", date(2026, 11, 5), date(2026, 12, 5), "PO-7003",
        [("Managed IT support, November", 1, "3200.00"), ("Laptop setup", 3, "150.00")], "C"),
    inv("invoice_04.pdf", "plover", "INV-3318", date(2026, 11, 6), date(2026, 11, 20), "PO-7004",
        [("Courier run, metro", 14, "38.00")], "A"),
    inv("invoice_05.pdf", "wattle", "INV-1187", date(2026, 11, 9), date(2026, 12, 9), "PO-7005",
        [("Reception signage panel", 2, "310.00")], "B"),
    inv("invoice_06.pdf", "saltbush", "INV-662", date(2026, 11, 10), date(2026, 12, 10), "PO-7006",
        [("Catering, client workshop (per head)", 30, "42.00"), ("Delivery", 1, "60.00")], "C"),
    inv("invoice_07.pdf", "plover", "INV-3320", date(2026, 11, 12), date(2026, 11, 26), None,        # no PO
        [("Courier run, metro", 9, "38.00")], "A"),
    inv("invoice_08.pdf", "heron", "INV-5521", date(2026, 11, 13), date(2026, 12, 13), "PO-7007",     # over PO
        [("Boardroom furniture hire, 4 weeks", 4, "1550.00")], "B"),
    inv("invoice_09.pdf", "banksia", "INV-2201", date(2026, 10, 30), date(2026, 11, 29), "PO-7001",  # duplicate of 01
        [("A4 copy paper (carton)", 20, "12.50"), ("Laser toner cartridge", 4, "85.00")], "C"),
    inv("invoice_10.pdf", "saltbush", "INV-671", date(2026, 11, 16), date(2026, 12, 16), "PO-7006",   # wrong line sum
        [("Catering, client workshop (per head)", 30, "42.00"), ("Delivery", 1, "60.00")], "A",
        printed_subtotal="1380.00"),
]


def money(x):
    return f"${x:,.2f}"


def fmt(layout, d):
    return {"A": f"{d.day} {d:%B %Y}", "B": f"{d:%d/%m/%Y}", "C": f"{d:%Y-%m-%d}"}[layout]


def newpage():
    pdf = FPDF(format="A4")
    pdf.set_creation_date(datetime(2026, 11, 20, tzinfo=timezone.utc))   # aware: a naive date takes the machine's UTC offset
    pdf.set_compression(False)   # zlib output differs between builds (e.g. zlib-ng); plain streams are byte-stable
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    return pdf


def line(pdf, text, h=6, style="", size=10, align="L"):
    pdf.set_font("Helvetica", style, size)
    pdf.cell(0, h, text, new_x="LMARGIN", new_y="NEXT", align=align)


def layout_a(i):
    """Classic: supplier block, meta lines, bordered table, right-aligned totals."""
    name, abn, addr = i["supplier"]
    pdf = newpage()
    line(pdf, name, 8, "B", 14)
    line(pdf, f"ABN {abn}")
    line(pdf, addr)
    pdf.ln(4)
    line(pdf, "TAX INVOICE", 10, "B", 18)
    line(pdf, f"Invoice No: {i['number']}")
    line(pdf, f"Invoice Date: {fmt('A', i['issued'])}")
    line(pdf, f"Due Date: {fmt('A', i['due'])}")
    if i["po"]:
        line(pdf, f"Purchase Order: {i['po']}")
    line(pdf, "Bill To: Copperleaf Advisory, Level 9, 1 Sample Street, Melbourne VIC 3000")
    pdf.ln(4)
    widths = (95, 20, 35, 35)
    pdf.set_font("Helvetica", "B", 10)
    for w, h in zip(widths, ("Description", "Qty", "Unit Price", "Amount")):
        pdf.cell(w, 7, h, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for d, q, p in i["lines"]:
        for w, v in zip(widths, (d, f"{q:g}", money(p), money(q * p))):
            pdf.cell(w, 7, v, border=1)
        pdf.ln()
    pdf.ln(3)
    line(pdf, f"Subtotal: {money(i['subtotal'])}", align="R")
    line(pdf, f"GST (10%): {money(i['tax'])}", align="R")
    line(pdf, f"Total (AUD): {money(i['total'])}", 8, "B", 12, align="R")
    pdf.ln(4)
    line(pdf, "Payment terms: 30 days. Please quote the invoice number with your payment.", size=9)
    return pdf


def layout_b(i):
    """Compact: INVOICE heading, labelled blocks, unbordered table, 'Amount due' footer."""
    name, abn, addr = i["supplier"]
    pdf = newpage()
    line(pdf, f"INVOICE #{i['number']}", 10, "B", 16)
    line(pdf, f"From: {name} (ABN {abn})")
    line(pdf, f"      {addr}")
    line(pdf, "To: Copperleaf Advisory, Accounts Payable")
    line(pdf, f"Issued: {fmt('B', i['issued'])}      Payment due: {fmt('B', i['due'])}")
    if i["po"]:
        line(pdf, f"Your ref (PO): {i['po']}")
    pdf.ln(5)
    for h in ("Item", "Qty", "Rate", "Line total"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell({"Item": 100, "Qty": 15, "Rate": 35, "Line total": 35}[h], 7, h)
    pdf.ln()
    for d, q, p in i["lines"]:
        pdf.set_font("Helvetica", "", 10)
        for w, v in zip((100, 15, 35, 35), (d, f"{q:g}", money(p), money(q * p))):
            pdf.cell(w, 7, v)
        pdf.ln()
    pdf.ln(4)
    line(pdf, f"Sub-total {money(i['subtotal'])}", align="R")
    line(pdf, f"GST {money(i['tax'])}", align="R")
    line(pdf, f"AMOUNT DUE (AUD) {money(i['total'])}", 8, "B", 12, align="R")
    return pdf


def layout_c(i):
    """Plain text: key-value lines and a numbered list of items, dates as ISO."""
    name, abn, addr = i["supplier"]
    pdf = newpage()
    line(pdf, name.upper(), 8, "B", 13)
    line(pdf, f"ABN: {abn}   |   {addr}", size=9)
    pdf.ln(3)
    line(pdf, "Tax invoice", 8, "B", 14)
    line(pdf, f"Invoice number: {i['number']}")
    line(pdf, f"Invoice date: {fmt('C', i['issued'])}")
    line(pdf, f"Due date: {fmt('C', i['due'])}")
    if i["po"]:
        line(pdf, f"PO number: {i['po']}")
    line(pdf, "Customer: Copperleaf Advisory")
    pdf.ln(3)
    line(pdf, "Items", 7, "B", 11)
    for n, (d, q, p) in enumerate(i["lines"], start=1):
        line(pdf, f"{n}. {d} - {q:g} @ {money(p)} = {money(q * p)}")
    pdf.ln(3)
    line(pdf, f"Subtotal (ex GST): {money(i['subtotal'])}")
    line(pdf, f"GST: {money(i['tax'])}")
    line(pdf, f"Total payable: {money(i['total'])} AUD", 8, "B", 11)
    return pdf


LAYOUTS = {"A": layout_a, "B": layout_b, "C": layout_c}


def answer(i, conf):
    name, abn, _ = i["supplier"]
    return {"supplier": name, "abn": abn, "invoice_number": i["number"], "invoice_date": i["issued"].isoformat(),
            "due_date": i["due"].isoformat(), "po_number": i["po"], "currency": "AUD",
            "line_items": [{"description": d, "qty": float(q), "unit_price": float(p), "amount": float(q * p)}
                           for d, q, p in i["lines"]],
            "subtotal": float(i["subtotal"]), "tax": float(i["tax"]), "total": float(i["total"]),
            "confidence": conf}


def main():
    inbox = fg.reset(HERE / "inbox", "*.pdf")
    answers = {}
    for n, i in enumerate(INVOICES):
        LAYOUTS[i["layout"]](i).output(str(inbox / i["file"]))
        answers[i["file"]] = answer(i, [0.97, 0.95, 0.93, 0.96, 0.94][n % 5])
    fg.write_csv(HERE / "reference" / "po_register.csv", ["po_number", "supplier", "amount", "status"], PO_REGISTER)
    fg.write_answers(HERE.name, answers)
    print(f"wrote {len(INVOICES)} invoices, po_register.csv and answers.json")


if __name__ == "__main__":
    main()
