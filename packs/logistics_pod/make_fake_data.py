"""Generate the fake delivery dockets for logistics_pod. Run:  python packs/logistics_pod/make_fake_data.py

10 docket photos drawn with Pillow (6 clean, 1 with an empty signature box, 1 with damage ticked and a note,
1 unknown consignment, 1 count mismatch), the shared Kestrel Freight shipment list, and the canned model answers
used by the tests. The signature is a random line. Seeded and repeatable. All businesses and people are fictional.
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import fakegen as fg  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

INK = (22, 38, 120)
BLACK = (25, 25, 25)

# consignment, received by, delivered (date, time), packages received, signed, damage note or None
DOCKETS = [
    ("KF-48201", "T. Morrison", ("2026-11-12", "10:42"), 4, True, None),
    ("KF-48202", "L. Okafor", ("2026-11-12", "14:05"), 2, True, None),
    ("KF-48203", "P. Hartley", ("2026-11-13", "09:18"), 6, True, None),
    ("KF-48204", "D. Nakamura", ("2026-11-13", "16:30"), 3, True, None),
    ("KF-48205", "S. Barrett", ("2026-11-16", "11:12"), 8, True, None),
    ("KF-48206", "J. Quinlan", ("2026-11-16", "13:47"), 12, True, None),
    ("KF-48207", "M. Castellano", ("2026-11-17", "10:20"), 5, False, None),                      # empty signature box
    ("KF-48208", "R. Gunawardena", ("2026-11-17", "15:05"), 7, True, "2 cartons crushed, 1 wet"),  # damage
    ("KF-48299", "A. Whitfield", ("2026-11-18", "09:40"), 2, True, None),                         # unknown consignment
    ("KF-48210", "C. Delacroix", ("2026-11-18", "12:25"), 7, True, None),                         # 9 sent, 7 received
]


def checkbox(d, x, y, label, ticked, f):
    d.rectangle((x, y, x + 20, y + 20), outline=BLACK, width=2)
    if ticked:
        d.line((x + 3, y + 3, x + 17, y + 17), fill=INK, width=3)
        d.line((x + 17, y + 3, x + 3, y + 17), fill=INK, width=3)
    d.text((x + 28, y - 1), label, fill=BLACK, font=f)


def signature(d, box, rng):
    """A random pen line inside the box."""
    x0, y0, x1, y1 = box
    pts, x = [], x0 + 15
    while x < x1 - 15:
        pts.append((x, rng.uniform(y0 + 20, y1 - 20)))
        x += rng.uniform(12, 28)
    d.line(pts, fill=INK, width=3, joint="curve")
    d.line([(x0 + 25, y1 - 22), (x1 - 40, y1 - 30 + rng.uniform(-8, 8))], fill=INK, width=2)


def render(docket, rng):
    cons, name, (day, hhmm), packages, signed, damage = docket
    y_, m_, d_ = day.split("-")
    img = Image.new("RGB", (760, 560), (252, 251, 247))
    d = ImageDraw.Draw(img)
    big, mid, small = fg.font(30, "bold"), fg.font(20), fg.font(17)
    d.rectangle((0, 0, 760, 70), fill=(26, 58, 99))
    d.text((24, 16), "KESTREL FREIGHT", fill="white", font=big)
    d.text((470, 26), "PROOF OF DELIVERY", fill="white", font=mid)

    d.text((30, 95), "Consignment No:", fill=BLACK, font=mid)
    d.text((220, 93), cons, fill=INK, font=fg.font(24, "bold"))
    d.text((30, 140), "Received by (print):", fill=BLACK, font=mid)
    d.text((250, 138), name, fill=INK, font=fg.font(24))
    d.text((30, 185), "Date / time delivered:", fill=BLACK, font=mid)
    d.text((270, 183), f"{d_}/{m_}/{y_}   {hhmm}", fill=INK, font=fg.font(24))
    d.text((30, 230), "Packages received:", fill=BLACK, font=mid)
    d.text((250, 228), str(packages), fill=INK, font=fg.font(26, "bold"))

    d.text((30, 280), "Damage noted:", fill=BLACK, font=mid)
    checkbox(d, 190, 281, "YES", damage is not None, mid)
    checkbox(d, 290, 281, "NO", damage is None, mid)
    d.text((30, 325), "Damage note:", fill=BLACK, font=small)
    d.line((140, 345, 730, 345), fill=BLACK, width=1)
    if damage:
        d.text((148, 320), damage, fill=INK, font=fg.font(22))

    d.text((30, 380), "Signature:", fill=BLACK, font=mid)
    box = (30, 405, 400, 520)
    d.rectangle(box, outline=BLACK, width=2)
    if signed:
        signature(d, box, rng)
    d.text((430, 480), "Driver copy. Keep for 12 months.", fill=(120, 120, 120), font=small)

    img = img.rotate(rng.uniform(-1.5, 1.5), resample=Image.BICUBIC, fillcolor=(214, 212, 206), expand=True)
    px = img.load()
    for _ in range(img.width * img.height // 120):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        v = rng.randrange(-14, 14)
        c = px[x, y]
        px[x, y] = tuple(max(0, min(255, c[k] + v)) for k in range(3))
    return img


def answer(docket, conf, **over):
    cons, name, (day, hhmm), packages, signed, damage = docket
    out = {"consignment_no": cons, "recipient_name": name, "delivered_at": f"{day} {hhmm}",
           "signature_present": signed, "damage_noted": damage is not None, "damage_note": damage,
           "packages_count": packages, "confidence": conf}
    out.update(over)
    return out


def main():
    inbox = fg.reset(HERE / "inbox", "*.png")
    fg.write_kestrel_csv(HERE.parent / "_shared" / "kestrel_shipments.csv")
    answers, rng = {}, random.Random(5550)
    for n, docket in enumerate(DOCKETS, start=1):
        name = f"docket_{n:02d}.png"
        render(docket, random.Random(900 + n)).save(inbox / name)
        answers[name] = answer(docket, round(rng.uniform(0.9, 0.97), 2))
    fg.write_answers(HERE.name, answers)
    print(f"wrote {len(DOCKETS)} dockets, kestrel_shipments.csv and answers.json")


if __name__ == "__main__":
    main()
