# ops-intake-agent

One engine, nine industry packs. **Claude extracts or classifies, code verifies, people review.**

**All data in this repo is fake. Nothing is ever sent.** Every organisation, person, address and amount is
invented. Email domains use the reserved `.example` TLD and phone numbers use the `03 5550 xxxx` range. The tool
writes reports, dashboards and draft files. It has no way to send an email, post a message or change a record.

## What the engine does

```
load  ->  extract  ->  check  ->  route  ->  act  ->  outputs
files     Claude      code        code       code     report.xlsx, dashboard.html,
          (JSON)      (rules)     (reasons)  (rows,   results.json, log.jsonl,
                                              drafts)  drafts/, work_orders/, reminders/
```

1. **Load** a folder of documents or messages (email, text, image, PDF, or CSV rows).
2. **Extract.** Claude reads each item and fills in a fixed JSON schema (or classifies it). It decides nothing else.
3. **Check.** Plain code verifies the result: arithmetic, dates, lookups against reference CSVs, duplicates.
4. **Route.** Code collects *every* reason an item needs a person. No reasons means `auto`. Any reason means `human`.
5. **Act.** For items that are safe to handle, code writes rows, work orders, reminders (`.ics`), and, where a pack
   asks, a second Claude call writes a reply *draft*.
6. **Outputs.** Per pack: an Excel report, a static HTML dashboard, JSON results, and a log of every step.

## The nine packs

Every organisation below is fictional.

| Pack | Organisation (fictional) | Input | Claude reads | Code checks | Fake data |
|---|---|---|---|---|---|
| `finance_receipts` | Copperleaf Advisory | receipt photos (PNG) | merchant, date, subtotal, GST, total, category | sum, GST 10%, date age, claimed amount, duplicate, 300 limit | 12: 7 clean, blurry, total cut off, duplicate, over limit, wrong GST |
| `finance_invoices` | Copperleaf Advisory | supplier invoice PDFs | supplier, ABN, dates, PO, lines, totals | line sum, total, due date, PO exists/open/supplier/amount, duplicate | 10: 6 clean, no PO, over PO, duplicate, wrong line sum |
| `logistics_pod` | Kestrel Freight | delivery docket photos | consignment, receiver, time, signature, damage, packages | known consignment, dates, signature, damage, package count | 10: 6 clean, no signature, damage, unknown consignment, count mismatch |
| `logistics_shipments` | Kestrel Freight | customer emails | category, consignment, urgency | consignment exists; damage, customs and address changes always to a person | 12 incl. 1 prompt injection, 2 vague |
| `hotel_messages` | Saltmarsh Suites | guest emails | category, booking ref, sentiment | booking exists; complaints, safety, stay changes always to a person | 12 incl. 1 prompt injection, 2 vague |
| `hotel_reviews` | Saltmarsh Suites | rows of a reviews CSV | topics, sentiment, health and legal flags | rating (from the CSV) of 2 or less; flags; promises or admissions in the draft | 15 incl. 1 health mention, 1 prompt injection |
| `property_maintenance` | Laneway Property Management | tenant emails | issue, urgency, hazard, property | property exists; hazards to a person with a fixed safety reply | 12 incl. a gas smell, 1 prompt injection, 2 vague |
| `property_leases` | Laneway Property Management | lease PDFs (one image-only) | tenants, term, rent, bond, notice | term order, rent, notice; renewal-decision reminder | 8: 5 clean, no notice, end before start, image-only |
| `construction_tenders` | Westgate Climate Services | tender emails + PDF summaries | project, trades, closing and site-visit dates | in scope, closed, closing within 3 business days, link | 10 incl. out of scope, closes tomorrow, no date, 1 prompt injection |

Each pack is a folder under `packs/` with `pack.py` (checks, routing, actions), `schema.json`, `prompt.md`,
`make_fake_data.py` (seeded and repeatable), the generated `inbox/` and `reference/` data, and tests.
`logistics_pod` and `logistics_shipments` share `packs/_shared/kestrel_shipments.csv`.

## How to run

Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest              # no network, no cost
```

Run one pack or all of them. Before any run the tool prints how many Claude calls it will make.

```powershell
# On your Claude plan, through the claude CLI (the demo path)
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
$env:BACKEND = "claude-code"
.\.venv\Scripts\python.exe run.py --pack finance_receipts
.\.venv\Scripts\python.exe run.py --all           # all packs, and outputs\index.html

# With an API key (the production path)
$env:BACKEND = "api"
$env:ANTHROPIC_API_KEY = "..."
$env:ANTHROPIC_MODEL = "<model id>"               # no default, on purpose
.\.venv\Scripts\python.exe run.py --pack finance_invoices
```

Open `outputs\<pack>\dashboard.html`, or `outputs\index.html` after `--all`. Each run starts from scratch and
replaces that pack's folder in `outputs\`. To rebuild the fake data: `python packs/<pack>/make_fake_data.py`.

Claude calls per live run (extract calls; packs that write replies also make up to one draft call per item, and a
retry can add one extract call per item):

| Pack | Extract calls | Possible draft calls |
|---|---|---|
| `finance_receipts` | 12 | 0 |
| `finance_invoices` | 10 | 0 |
| `logistics_pod` | 10 | 0 |
| `logistics_shipments` | 12 | 12 |
| `hotel_messages` | 12 | 12 |
| `hotel_reviews` | 15 | 15 |
| `property_maintenance` | 12 | 0 |
| `property_leases` | 8 | 0 |
| `construction_tenders` | 10 | 0 |

### Settings

Only `engine/config.py` reads environment variables.

| Variable | Meaning |
|---|---|
| `BACKEND` | `api` (default) or `claude-code` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | required for `api`; `ANTHROPIC_MODEL` has no default. For `claude-code` the model is optional. |
| `IMAGE_MODE` | `vision` (default for both backends) or `tesseract` |
| `CLAUDE_CODE_TIMEOUT` | seconds per `claude -p` call, default 120 |
| `DEMO_TODAY` | `YYYY-MM-DD`, default `2026-11-20`. Every date check uses this, never the real clock. |

## The backends

- **`api`** is the production path. It uses the Anthropic SDK with the JSON-schema output format, and sends images
  as base64 image blocks.
- **`claude-code`** is the demo path. It runs `claude -p` as a subprocess, so it uses a Claude plan instead of API
  billing. On every call: `--tools ""` (the input is untrusted, so the model gets no file or shell tools),
  `--no-session-persistence`, the input goes in through stdin and never the command line, a timeout, and
  `--json-schema` so the answer arrives as `structured_output`.
- **Images.** Both backends default to `IMAGE_MODE=vision`, where Claude reads the image directly. For the CLI,
  `scripts/image_test.py` showed that a base64 image sent as a stream-json message on stdin works with tools off.
  `IMAGE_MODE=tesseract` is optional: local OCR makes text and Claude structures the text. It needs Tesseract
  installed.
- A PDF with no text layer goes through the same image path. If that path is not available, the item goes to a
  person as `no_text_layer`.

## Design decisions and core rules

1. **Input is untrusted.** Documents go inside `<document>` tags (a forged closing tag is neutralised), and the
   prompt says to ignore any instruction inside them. Every text pack has a prompt-injection item in its fake data.
2. **Schema-enforced JSON, validated again in code:** enums, ranges, types, required fields.
3. **Retry once** on a failed call or invalid output. **JSON is never repaired.** A second failure sends the item to
   a person (`extract_failed`), and the bad output is logged.
4. **Fail safe.** Any error, timeout or refusal sends the item to a person. A pack's `route()` can never send an
   item with a failure reason to `auto`.
5. **Confidence.** Every schema has `confidence` from 0 to 1. Below 0.8 goes to a person (`low_confidence`).
   Exactly 0.8 counts as confident.
6. **The model extracts, code verifies.** Arithmetic, dates, lookups and duplicates are checked in code. The model
   never decides a route.
7. **All reasons.** Routing returns a list. Every reason that applies is logged and shown.
8. **Never send.** Drafts start with `DRAFT - NOT SENT` and use `[STAFF TO CONFIRM: ...]` instead of invented
   facts, prices or dates. Facts in a reply (a shipment status, a guest's dates) are inserted by code from the
   reference data.
9. **Log everything** to `log.jsonl`: timestamp, pack, item, step, output, confidence, backend, `retried`,
   `first_error` (cut to 100 characters), and `raw_output` when a retry also fails.
10. **CLI safety:** tools off, no session persistence, stdin only, timeout.
11. **Fake data only,** with fictional organisations, `.example` domains and `03 5550 xxxx` phone numbers.
12. **Fixed demo date** (`DEMO_TODAY`), so the demo gives the same result in any year.

Also: spreadsheet and CSV cells cannot run as formulas, everything that reaches HTML is escaped, output file names
cannot leave their folder, and the dashboards load nothing from the network.

## Results from live runs

**No pack has been run live yet.** This section will list real numbers per pack after each live run, and nothing
else. Everything else in this README describes how the tool is built, not what a live run produced.

The one live check so far is the image test (`scripts/image_test.py`), run once on the `claude-code` backend with a
generated PNG that reads `TOTAL 12.50`:

- Sending the image as a stream-json message with `--output-format stream-json --verbose` and tools off returned
  `{"total": 12.5}`.
- Sending the same input with `--output-format json` failed: the CLI requires stream-json output when the input is
  stream-json.
- Tesseract was not installed on that machine.

## Known limits

- **Confidence is the model's self-report.** It is not a calibrated probability. Code checks matter more.
- **The fake layouts are cleaner than real ones.** Real receipts, scans and emails are messier.
- **No connection to email, accounting or property systems.** Inputs are files in folders; outputs are files.
- **Each run starts from scratch.** There is no memory between runs, so a duplicate is only found within one run.
- **Inputs are sent to Claude.** Do not point this at documents you may not share with the service you use.
- **Drafts can be wrong.** Staff must read every draft. The code checks catch some problems (promises, admissions,
  missing placeholders), not all.
- **The `api` backend is the production path and has not been run live.** It is covered by tests with a mocked SDK
  client. The `claude-code` backend has had only the image test described above.
- Business-day counts ignore public holidays.

## Layout

```
run.py                     python run.py --pack <name> | --all
engine/                    pipeline, config, backends (api, claude_code), inputs, ocr, checks, drafts, outputs, ics
packs/<pack>/              pack.py, schema.json, prompt.md, make_fake_data.py, inbox/, reference/
packs/_shared/             reference CSVs used by two packs
scripts/                   image_test.py, fakegen.py (helpers for the fake-data generators)
tests/                     mock-backend tests, per-pack fixtures in tests/fixtures/<pack>/
outputs/                   written by a run; git-ignored
SPEC.md                    the design spec
```

## Licence

MIT. See `LICENSE`.
