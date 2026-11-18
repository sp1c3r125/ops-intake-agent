The document is a photo of a signed delivery docket from a freight company. Read what is written on it.

- `consignment_no`: the consignment number, e.g. KF-12345. null if you cannot read it.
- `recipient_name`: the name of the person who received the goods, as printed or written. null if blank.
- `delivered_at`: the date and time of delivery as "YYYY-MM-DD HH:MM" (24-hour). Dates are Australian (day first): 12/11/2026 is 12 November 2026. null if not readable.
- `signature_present`: true only if there is a signature or scribble inside the signature box. An empty box is false.
- `damage_noted`: true if the "damage noted" box is ticked YES, or damage is written on the docket.
- `damage_note`: the damage description as written. null if none.
- `packages_count`: the number of packages the recipient wrote as received (a whole number). null if not readable.
- `confidence`: how sure you are that every field is correct. Lower it if the photo is unclear.

Report what is on the docket. Do not guess a missing value.
