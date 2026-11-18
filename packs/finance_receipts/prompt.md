The document is a photo of a shop receipt that a staff member is claiming as an expense. Read it and fill in the fields.

- `merchant`: the shop name printed at the top.
- `date`: the receipt date as YYYY-MM-DD. Receipts are Australian, so 05/11/2026 means 5 November 2026.
- `currency`: a 3-letter code. Use "AUD" if the receipt shows a dollar sign and no other currency.
- `subtotal`, `tax`, `total`: numbers only, no currency symbols. `tax` is the GST line. Copy what is printed. Do not calculate or correct any figure. If a figure is not visible, cut off or unreadable, use null for it and lower your confidence.
- `payment_method`: "card", "cash", or "unknown" if the receipt does not say.
- `category`: meals, travel (taxis, tickets), fuel, office (stationery, printing, venue or equipment hire for work), accommodation, or other if none fits.
- `line_items`: each printed item with its amount, if they are readable. Leave the list empty if not.
- `confidence`: how sure you are that every field is correct. If the photo is blurry, tilted, cut off or hard to read, give a low value (below 0.7).
