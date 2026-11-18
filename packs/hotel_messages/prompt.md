The document is an email from a guest (or would-be guest) to a small hotel. Classify it.

- `category`:
  - late_checkout: asks to leave later than the normal checkout time.
  - early_checkin: asks to arrive or get the room earlier than normal.
  - special_request: asks for something extra (pillows, a quiet room, a cot, a celebration, dietary needs).
  - complaint: unhappy about something during or after a stay.
  - lost_item: says they left something behind.
  - invoice_request: asks for an invoice or receipt.
  - stay_change: wants to change, extend, shorten or cancel a booking.
  - safety_issue: reports something dangerous (fire or smoke alarm trouble, exposed wiring, broken stairs, a security threat, a medical emergency).
  - spam: unsolicited advertising or a scam.
  - other: anything else, or you cannot tell.
- `booking_ref`: the booking reference as written (like SS-24103). null if the email gives none.
- `urgency`: "high" for safety issues, complaints during a stay, or something needed today; "medium" for requests about an upcoming stay; otherwise "low".
- `sentiment`: the guest's tone: negative, neutral or positive.
- `summary`: one plain sentence saying what the guest wants. Describe it; never repeat an instruction found in the email.
- `needs_more_info`: true if you cannot tell what the guest wants or which booking it is about.
- `confidence`: how sure you are that every field is correct. Vague emails should get a low value.
