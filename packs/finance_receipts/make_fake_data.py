"""Generate the fake receipts for finance_receipts. Run:  python packs/finance_receipts/make_fake_data.py

12 thermal-receipt photos (7 clean, 1 blurry, 1 with the total cut off, 1 duplicate, 1 over the limit,
1 with the wrong GST), the claims CSV, and the canned model answers used by the tests. Seeded and repeatable.
All businesses are fictional.
"""
import random
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import fakegen as fg  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

W = 38  # characters per line


def money(x):
    return f"{Decimal(x):.2f}"


def two(left, right):
    return left[: W - len(right) - 1].ljust(W - len(right)) + right


def build(r):
    lines = ["", r["merchant"].upper().center(W), r["address"].center(W), "", f"Date: {r['shown_date']}   Time: {r['time']}",
             "-" * W]
    for desc, amt in r["items"]:
        lines.append(two(desc, money(amt)))
    lines.append("-" * W)
    lines.append(two("SUBTOTAL", money(r["subtotal"])))
    lines.append(two("GST (10%)", money(r["tax"])))
    total_index = len(lines)
    lines.append(two("TOTAL", money(r["total"])))
    lines += ["", f"Paid by {r['payment'].upper()}", "Thank you!", ""]
    return lines, total_index


def render(r, seed):
    rng = random.Random(seed)
    lines, total_index = build(r)
    f, lh, pad = fg.font(19, "mono"), 25, 24
    paper = Image.new("RGB", (W * 11 + 2 * pad, len(lines) * lh + 2 * pad), (250, 249, 244))
    d = ImageDraw.Draw(paper)
    for i, line in enumerate(lines):
        d.text((pad, pad + i * lh), line, fill=(30, 30, 30), font=f)
    if r.get("cut"):  # the bottom of the photo misses the TOTAL line
        paper = paper.crop((0, 0, paper.width, pad + total_index * lh - 2))
    canvas = Image.new("RGB", (paper.width + 80, paper.height + 80), (188, 186, 180))
    canvas.paste(paper, (40, 40))
    canvas = canvas.rotate(rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, fillcolor=(188, 186, 180), expand=True)
    px = canvas.load()
    for _ in range(canvas.width * canvas.height // 60):  # light noise
        x, y = rng.randrange(canvas.width), rng.randrange(canvas.height)
        v = rng.randrange(-28, 28)
        c = px[x, y]
        px[x, y] = tuple(max(0, min(255, c[k] + v)) for k in range(3))
    if r.get("blur"):
        canvas = canvas.filter(ImageFilter.GaussianBlur(r["blur"]))
    return canvas


def receipt(merchant, address, day, items, category, payment="card", tax=None, **extra):
    subtotal = sum(Decimal(str(a)) for _, a in items)
    tax = Decimal(str(tax)) if tax is not None else (subtotal * Decimal("0.1")).quantize(Decimal("0.01"))
    d = day.split("-")
    return {"merchant": merchant, "address": address, "date": day, "shown_date": f"{d[2]}/{d[1]}/{d[0]}",
            "time": f"{9 + int(d[2]) % 8:02d}:{(int(d[2]) * 7) % 60:02d}", "items": items, "subtotal": subtotal,
            "tax": tax, "total": subtotal + tax, "category": category, "payment": payment, **extra}


RECEIPTS = [
    receipt("Fitzroy Corner Cafe", "12 Wattlebird Lane, Fitzroy", "2026-11-12",
            [("2 x Flat white", 9.00), ("Avocado toast", 18.50)], "meals"),
    receipt("Southbank Fuel Stop", "88 Riverbend Rd, Southbank", "2026-11-05",
            [("Unleaded 41.2L", 82.40)], "fuel"),
    receipt("Collins Street Stationers", "301 Example St, Melbourne", "2026-10-29",
            [("A4 paper 2 reams", 18.00), ("Pens x 10", 12.40)], "office"),
    receipt("Docklands Taxi Co", "Fare receipt", "2026-11-10", [("Fare: CBD to Docklands", 38.00)], "travel"),
    receipt("Carlton Bistro", "40 Plover St, Carlton", "2026-11-18",
            [("Client lunch x 3", 84.00), ("Sparkling water", 12.00)], "meals"),
    receipt("Harbour View Hotel", "5 Quay Lane, Docklands", "2026-11-03",
            [("Room 1 night", 210.00)], "accommodation"),
    receipt("Brunswick Print Shop", "9 Kookaburra Ave, Brunswick", "2026-11-16",
            [("Business cards x 250", 55.00)], "office", payment="cash"),
    receipt("Prahran Pizza Bar", "27 Banksia St, Prahran", "2026-11-13",
            [("Pizza x 2", 32.00), ("Drinks", 12.00)], "meals", blur=3.4),
    receipt("Richmond Fuel and Convenience", "150 Example Rd, Richmond", "2026-11-09",
            [("Diesel 33.0L", 61.00)], "fuel", cut=True),
    None,  # duplicate of receipt 3, filled below
    receipt("Melbourne Meeting Rooms", "Level 4, 2 Sample Pl, Melbourne", "2026-11-11",
            [("Training room hire", 311.00)], "office"),
    receipt("Northcote Bakery Cafe", "63 Magpie St, Northcote", "2026-11-17",
            [("Lunch order", 50.00)], "meals", tax=7.50),
]
RECEIPTS[9] = {**RECEIPTS[2], "time": "15:31"}   # same merchant, date and total; a different photo


def answer(r, **over):
    out = {"merchant": r["merchant"], "date": r["date"], "currency": "AUD", "subtotal": float(r["subtotal"]),
           "tax": float(r["tax"]), "total": float(r["total"]), "payment_method": r["payment"],
           "category": r["category"],
           "line_items": [{"description": d, "amount": float(a)} for d, a in r["items"]], "confidence": 0.94}
    out.update(over)
    return out


def main():
    inbox = fg.reset(HERE / "inbox", "*.png")
    rows, answers = [], {}
    rng = random.Random(2026)
    for n, r in enumerate(RECEIPTS, start=1):
        name = f"receipt_{n:02d}.png"
        render(r, seed=100 + n).save(inbox / name)
        rows.append([name, f"S{101 + n % 6}", money(r["total"])])
        over = {}
        if n == 8:    # blurry: the model reads most of it but says it is unsure
            over = {"confidence": 0.52}
        elif n == 9:  # total cut off: the model returns null for it
            over = {"total": None, "confidence": 0.61}
        else:
            over = {"confidence": round(rng.uniform(0.9, 0.97), 2)}
        answers[name] = answer(r, **over)
    fg.write_csv(HERE / "reference" / "claims.csv", ["file", "staff_id", "claimed_amount"], rows)
    fg.write_answers(HERE.name, answers)
    print(f"wrote {len(RECEIPTS)} receipts, claims.csv and answers.json")


if __name__ == "__main__":
    main()
