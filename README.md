# Invoice → Decision

Upload an invoice PDF and get a decision, **APPROVE**, **HOLD** or **REJECT**, with a plain-English reason and a stage-by-stage trace of how it got there.

**Live demo:** https://invoiceproceapprdemo.streamlit.app/

## How it works

```
Ingest → Extract → Validate → Match PO → Check rules → Decide → Log
```

**Claude reads, rules decide.** Claude (`claude-sonnet-5`) is used only to extract the invoice fields, with a confidence score per field. Every decision is made by plain Python rules, so the same invoice always gets the same answer and every answer can be explained.

The rules run in this order, and the first one that fails decides the outcome:

| # | Check | Outcome if it fails | Example reason |
|---|-------|---------------------|----------------|
| 1 | Invoice number, vendor and total are present | HOLD | Missing: total |
| 2 | Key fields were read with confidence ≥ 0.8 | HOLD | Low confidence reading total, please verify |
| 3 | Vendor is on the approved list | REJECT | Vendor not on approved list |
| 4 | Not already processed | REJECT | Duplicate of invoice INV-0045, already processed on … |
| 5 | A PO is referenced, or can be confidently inferred | HOLD | No matching PO found |
| 6 | Already-approved billing plus this invoice ≤ PO amount + 2% | HOLD | PO PO-4531 would be over-billed by INR 8,500.00 |
| 7 | All checks pass | APPROVE | Matches PO PO-4512 within tolerance |

Every run is saved to SQLite and shown on the dashboard, together with its full trace.

## Edge cases covered

| Case | Scenario | Result |
|------|----------|--------|
| EC1 | Scanned (image-only) invoice with a blurry total | HOLD: low confidence |
| EC2 | One PO split across 3 invoices; the 3rd over-bills | APPROVE, APPROVE, HOLD |
| EC3 | Same invoice re-sent as `INV-0045` and then `INV-45` | REJECT: duplicate |
| EC4 | No PO number; inferred from vendor + line items | APPROVE, marked "PO inferred" |

## Run it locally

Tested with Python 3.13.

```bash
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml`. This file is git-ignored.

```toml
ANTHROPIC_API_KEY = "your-key"
```

Then start the app:

```bash
streamlit run app.py
```

In the sidebar, **Reset demo data** clears the run history, and the sample buttons load each test invoice, happy paths first.

**Tests:** `python run_tests.py` resets the database and runs all 8 sample invoices in order, checking each decision and reason. It calls the Claude API once per invoice.

**Test data:** `python scripts/make_test_data.py` regenerates `data/*.csv` and `test_invoices/*.pdf`. It needs Pillow, which is only used to produce the scanned EC1 invoice.

## Project layout

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI: Workspace tab (upload, queue, live decision feed), Dashboard tab, sidebar |
| `styles.css` | Visual design (fonts, colours, cards, feed bubbles), loaded by `app.py` |
| `pipeline.py` | Runs the stages in order, emits `{stage, status, detail}` trace entries, saves the run |
| `extract.py` | Sends the PDF to Claude and validates the JSON it returns |
| `models.py` | Pydantic `Invoice` / `LineItem` schema with per-field confidence |
| `rules.py` | The decision rules, in one ordered list |
| `db.py` | SQLite tables for run history and processed invoices |
| `config.py` | Confidence cutoff, tolerance, display time zone (IST), file paths |
| `data/` | Approved vendors and purchase orders |
| `test_invoices/` | Generated sample invoices |

See [ASSUMPTIONS.md](ASSUMPTIONS.md) for the assumptions behind these rules.

## What's next

- Email-inbox ingestion instead of manual upload
- 3-way match with goods-receipt (GRN) data
- A human-review queue for HOLDs, with approve/override actions
- Tracking override rates to tune the confidence and tolerance thresholds
- A rule that flags an invoice citing a PO that belongs to a different vendor
- Logging failed extractions to the run history
- Multi-currency support and role-based access
