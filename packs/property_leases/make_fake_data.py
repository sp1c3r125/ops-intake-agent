"""Generate the fake leases for property_leases. Run:  python packs/property_leases/make_fake_data.py

8 lease PDFs in three fpdf2 layouts: 5 clean, 1 with no notice period, 1 whose end date is before its start date
(a typo), and 1 that is only a picture of a page, with no text layer. Also the canned model answers for the tests.
All tenants, addresses and the agency are fictional.
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import fakegen as fg  # noqa: E402

AGENT = "Laneway Property Management"


def lease(file, tenants, address, start, end, rent, freq, bond, renewal, notice, conditions, layout, printed_end=None):
    return {"file": file, "tenants": tenants, "address": address, "start": start, "end": end,
            "printed_end": printed_end or end, "rent": rent, "freq": freq, "bond": bond, "renewal": renewal,
            "notice": notice, "conditions": conditions, "layout": layout}


LEASES = [
    lease("lease_01.pdf", ["Isabel Crowe", "Tom Crowe"], "Unit 3, 44 Starling Street, Footscray VIC 3011",
          date(2026, 2, 1), date(2027, 1, 31), 520, "weekly", 2080, True, 60, ["No pets without written consent"], "A"),
    lease("lease_02.pdf", ["Kwame Mensah"], "18 Bottlebrush Drive, Werribee VIC 3030",
          date(2026, 6, 15), date(2027, 6, 14), 2350, "monthly", 2350, False, 90,
          ["Tenant maintains the garden", "No smoking inside the property"], "B"),
    lease("lease_03.pdf", ["Linh Tran"], "Unit 9, 5 Kookaburra Close, Doncaster VIC 3108",
          date(2026, 9, 1), date(2027, 8, 31), 980, "fortnightly", 1960, False, 60,
          ["Smoke alarms tested every three months by the tenant"], "C"),
    lease("lease_04.pdf", ["Edwina Prowse", "Callum Prowse"], "27 Sandpiper Road, Sunbury VIC 3429",
          date(2026, 3, 1), date(2027, 2, 28), 430, "weekly", 1720, True, 30, [], "A"),
    lease("lease_05.pdf", ["Rafael Medina"], "Unit 14, 200 Lorikeet Avenue, Box Hill VIC 3128",
          date(2026, 1, 15), date(2027, 1, 14), 2900, "monthly", 2900, False, 45,
          ["One small pet (cat) approved"], "B"),
    lease("lease_06.pdf", ["Zoe Harcourt"], "6 Finch Place, Altona VIC 3018",                  # no notice period stated
          date(2026, 10, 1), date(2027, 9, 30), 610, "weekly", 2440, False, None, [], "C"),
    lease("lease_07.pdf", ["Marcus Oyelaran"], "Unit 21, 90 Wombat Way, Sunshine VIC 3020",     # end date typo: 2025
          date(2026, 9, 1), date(2027, 8, 31), 495, "weekly", 1980, False, 60, [], "A",
          printed_end=date(2025, 8, 31)),
    lease("lease_08.pdf", ["Sienna Valdez"], "Unit 6, 12 Gannet Street, Brunswick VIC 3056",    # image only
          date(2026, 8, 1), date(2027, 7, 31), 2600, "monthly", 2600, True, 60,
          ["Tenant to arrange carpet cleaning at the end of the lease"], "IMAGE"),
]


def money(x):
    return f"${x:,.2f}"


def long_date(d):
    return f"{d.day} {d:%B %Y}"


def a_lines(L):
    """Formal clauses (layout A, and the picture-only lease)."""
    names = " and ".join(L["tenants"])
    out = [("RESIDENTIAL TENANCY AGREEMENT", 16, "B"), (f"Agent: {AGENT}", 10, ""), ("", 10, ""),
           ("1. The parties", 12, "B"), (f"The Landlord's agent is {AGENT}. The Tenant(s): {names}.", 10, ""),
           ("2. The premises", 12, "B"), (f"The premises are located at {L['address']}.", 10, ""),
           ("3. Term", 12, "B"),
           (f"The tenancy begins on {long_date(L['start'])} and ends on {long_date(L['printed_end'])}.", 10, ""),
           ("4. Rent and bond", 12, "B"),
           (f"The rent is {money(L['rent'])} payable {L['freq']} in advance. The Tenant must pay a bond of "
            f"{money(L['bond'])}.", 10, ""),
           ("5. Renewal and notice", 12, "B"),
           ("The Tenant has an option to renew this agreement for a further 12 months." if L["renewal"]
            else "There is no option to renew this agreement.", 10, "")]
    if L["notice"] is not None:
        out.append((f"Either party must give not less than {L['notice']} days written notice of intention to end "
                    f"or renew the tenancy.", 10, ""))
    out.append(("6. Special conditions", 12, "B"))
    out += [(f"- {c}.", 10, "") for c in L["conditions"]] or [("None.", 10, "")]
    return out


def layout_a(L):
    pdf = new_pdf()
    for text, size, style in a_lines(L):
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, 6.5 if size < 14 else 9, text, new_x="LMARGIN", new_y="NEXT")
    return pdf


def layout_b(L):
    """A summary table of labels and values, dates as dd/mm/yyyy."""
    pdf = new_pdf()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, "LEASE SUMMARY SCHEDULE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Prepared by {AGENT}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    rows = [("Tenant(s)", "; ".join(L["tenants"])), ("Premises", L["address"]),
            ("Lease start", f"{L['start']:%d/%m/%Y}"), ("Lease end", f"{L['printed_end']:%d/%m/%Y}"),
            ("Rent", f"{money(L['rent'])} per {({'weekly': 'week', 'fortnightly': 'fortnight', 'monthly': 'month'})[L['freq']]}"),
            ("Bond", money(L["bond"])),
            ("Renewal", "Option to renew for 12 months" if L["renewal"] else "No renewal option"),
            ("Notice period", f"{L['notice']} days" if L["notice"] is not None else "-"),
            ("Special conditions", "; ".join(L["conditions"]) or "Nil")]
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(45, 8, label, border=1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 8, value, border=1, new_x="LMARGIN", new_y="NEXT")
    return pdf


def layout_c(L):
    """Narrative paragraphs."""
    pdf = new_pdf()
    names = " and ".join(L["tenants"])
    paras = [f"LEASE AGREEMENT - {AGENT.upper()}",
             f"This lease is made between {AGENT} (as agent for the owner) and {names} (the tenant) for the "
             f"residence at {L['address']}.",
             f"The lease commences on {L['start']:%Y-%m-%d} and expires on {L['printed_end']:%Y-%m-%d}.",
             f"The tenant will pay {money(L['rent'])} {L['freq']}. A security bond of {money(L['bond'])} is "
             f"held for the term of the lease."]
    paras.append("The tenant may request to renew the lease for a further 12 months." if L["renewal"]
                 else "The lease does not include a right of renewal.")
    if L["notice"] is not None:
        paras.append(f"Written notice of {L['notice']} days is required to end or renew the tenancy.")
    paras.append("Additional terms: " + ("; ".join(L["conditions"]) + "." if L["conditions"] else "none agreed."))
    for i, p in enumerate(paras):
        pdf.set_font("Helvetica", "B" if i == 0 else "", 13 if i == 0 else 10.5)
        pdf.multi_cell(0, 7, p, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    return pdf


def new_pdf():
    pdf = FPDF(format="A4")
    pdf.set_creation_date(datetime(2026, 11, 20, tzinfo=timezone.utc))   # aware: a naive date takes the machine's UTC offset
    pdf.set_compression(False)   # zlib output differs between builds (e.g. zlib-ng); plain streams are byte-stable
    pdf.add_page()
    return pdf


def picture_only(L, path):
    """Draw the formal lease onto an image and save it as a PDF: there is no text layer to read."""
    w, h = 1240, 1754
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    y = 90
    for text, size, style in a_lines(L):
        f = fg.font(int(size * 2.6), "bold" if style else "sans")
        # wrap to the page width
        words, line = text.split(), ""
        for word in words or [""]:
            trial = f"{line} {word}".strip()
            if d.textlength(trial, font=f) > w - 180 and line:
                d.text((90, y), line, fill=(20, 20, 20), font=f)
                y += int(size * 3.3)
                line = word
            else:
                line = trial
        d.text((90, y), line, fill=(20, 20, 20), font=f)
        y += int(size * 3.6)
    fixed = datetime(2026, 11, 20).timetuple()   # Pillow would otherwise stamp the current time
    img.save(path, "PDF", resolution=150.0, creationDate=fixed, modDate=fixed)


def answer(L, conf):
    return {"tenant_names": L["tenants"], "property_address": L["address"], "start_date": L["start"].isoformat(),
            "end_date": L["printed_end"].isoformat(), "rent_amount": float(L["rent"]), "rent_frequency": L["freq"],
            "bond_amount": float(L["bond"]), "renewal_option": L["renewal"], "notice_days": L["notice"],
            "special_conditions": L["conditions"], "confidence": conf}


def main():
    inbox = fg.reset(HERE / "inbox", "*.pdf")
    answers = {}
    for n, L in enumerate(LEASES):
        path = inbox / L["file"]
        if L["layout"] == "IMAGE":
            picture_only(L, path)
        else:
            {"A": layout_a, "B": layout_b, "C": layout_c}[L["layout"]](L).output(str(path))
        answers[L["file"]] = answer(L, [0.96, 0.94, 0.95, 0.93, 0.97][n % 5] if L["layout"] != "IMAGE" else 0.9)
    fg.write_answers(HERE.name, answers)
    print(f"wrote {len(LEASES)} leases and answers.json")


if __name__ == "__main__":
    main()
