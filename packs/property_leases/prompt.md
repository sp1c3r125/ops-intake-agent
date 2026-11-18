The document is a residential lease (tenancy agreement), as text or as an image of its pages. Read it and fill in the fields exactly as the lease states them.

- `tenant_names`: every tenant named, one entry per person.
- `property_address`: the address of the rented property.
- `start_date` and `end_date`: as YYYY-MM-DD. Dates are Australian (day first): 01/02/2026 is 1 February 2026. Copy the dates as printed, even if they look wrong (for example an end date before the start date). Our system checks them.
- `rent_amount`: the rent for one period, as a number without symbols. null if the lease states no rent.
- `rent_frequency`: "weekly", "fortnightly" or "monthly". null if not stated.
- `bond_amount`: the bond (security deposit) as a number. null if not stated.
- `renewal_option`: true only if the lease gives the tenant an option or right to renew. false if it says there is none or says nothing.
- `notice_days`: the number of days of written notice the lease requires for ending or renewing the tenancy, as a whole number. null if the lease does not state a notice period. Do not guess one.
- `special_conditions`: each special or additional condition, as a short phrase (for example "No pets without written consent"). An empty list if there are none.
- `confidence`: how sure you are that every field is correct. Lower it if the text is unclear or hard to read.
