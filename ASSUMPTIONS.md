# Assumptions

These are the choices this demo makes where a real client would give us their own policy. Each one is configurable or isolated in one place, so changing it doesn't mean rewriting the system.

| # | Assumption | Would change if… |
|---|------------|------------------|
| A1 | Invoices arrive as a single PDF upload, not from an email inbox | The client wants inbox or email ingestion |
| A2 | 2-way match (invoice ↔ PO); no goods-receipt check | The client has goods-receipt (GRN) data for a 3-way match |
| A3 | Over-billing tolerance is 2% of the PO amount (`TOLERANCE_PERCENT` in `config.py`), and the invoices already approved against a PO count toward it | The client gives their own tolerance policy |
| A4 | INR only; one PO per invoice | Multi-currency or multi-PO invoices |
| A5 | A key field (vendor, invoice number, total) read with confidence below 0.8 (`CONFIDENCE_CUTOFF`) goes to a human | Real override data shows the threshold is too strict or too loose |
| A6 | A duplicate means the same vendor, the same total, and the same invoice number once formatting is ignored (`INV-0045` = `INV-45`) | The client also treats same-vendor, same-amount, same-date invoices as suspect |
| A7 | Vendor names and PO numbers are matched after ignoring case, punctuation and "Private Limited" vs "Pvt Ltd"; there is no fuzzy matching | The vendor master has inconsistent spellings that need fuzzy matching with review |
| A8 | When an invoice has no PO number, a PO is inferred only if exactly one of that vendor's POs contains every invoice line item; otherwise it is held | The client prefers inference to be looser or turned off |
| A9 | The approved vendors (`data/vendors.csv`) and open POs (`data/pos.csv`) are static files | Reference data comes from the client's ERP |
| A10 | The LLM only reads the invoice. Every decision is made by fixed Python rules in a set order | No change: this keeps decisions explainable, repeatable and testable |
