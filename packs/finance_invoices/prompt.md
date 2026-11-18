The document is the text of a supplier's invoice sent to Copperleaf Advisory. Read it and fill in the fields exactly as printed.

- `supplier`: the business that issued the invoice (not Copperleaf Advisory, which is the customer).
- `abn`: the supplier's ABN as printed.
- `invoice_number`: the invoice number as printed.
- `invoice_date` and `due_date`: as YYYY-MM-DD. Dates are Australian (day first): 05/11/2026 is 5 November 2026.
- `po_number`: the purchase order number if one is printed (it may be labelled "PO", "Purchase order" or "Your ref"). null if the invoice shows none.
- `currency`: a 3-letter code. "AUD" if amounts have a dollar sign and no other currency is named.
- `line_items`: every line with its description, quantity, unit price and line amount, as printed.
- `subtotal`, `tax`, `total`: the printed figures, as numbers without symbols. Copy them. Do not add up, correct or recalculate anything, even if the figures look wrong: our system checks the arithmetic.
- `confidence`: how sure you are that every field is correct. Lower it if anything is unclear or missing.
