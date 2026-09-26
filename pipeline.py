import csv
from pathlib import Path
from typing import Callable

from config import DB_PATH, POS_PATH, VENDORS_PATH
from db import connect, processed_invoices, save_processed_invoice, save_run
from extract import extract_invoice
from models import Invoice
from rules import RULES, RuleContext, normalise_invoice_no


def _load_vendors(path: Path = VENDORS_PATH) -> set[str]:
    with path.open(newline="", encoding="utf-8") as file:
        return {row["vendor"] for row in csv.DictReader(file)}


def _load_pos(path: Path = POS_PATH) -> dict[str, dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as file:
        return {
            row["po_number"]: {
                "vendor": row["vendor"],
                "amount": row["amount"],
                "line_items": [item.strip() for item in row["line_items"].split(";")],
            }
            for row in csv.DictReader(file)
        }


def process_invoice(pdf_path: str | Path, on_trace: Callable[[dict[str, str]], None] | None = None,
                    db_path: str | Path = DB_PATH,
                    extractor: Callable[[str | Path], Invoice] = extract_invoice) -> dict[str, object]:
    trace: list[dict[str, str]] = []

    def add_trace(stage: str, status: str, detail: str) -> None:
        entry = {"stage": stage, "status": status, "detail": detail}
        trace.append(entry)
        if on_trace:
            on_trace(entry)

    path = Path(pdf_path)
    add_trace("ingest", "ok", f"Received {path.name}")
    invoice = extractor(path)
    add_trace("extract", "ok", "Invoice fields extracted with confidence scores")

    with connect(db_path) as connection:
        context = RuleContext(
            invoice=invoice,
            vendors=_load_vendors(),
            pos=_load_pos(),
            processed=processed_invoices(connection),
        )
        for rule in RULES:
            result = rule(context)
            status = "ok" if result.passed else "warn"
            add_trace(rule.__name__, status, result.reason)
            if result.outcome is not None:
                decision, reason = result.outcome, result.reason
                break
        else:
            decision, reason = "APPROVE", "All checks passed"

        add_trace("decide", "ok", f"{decision}: {reason}")
        add_trace("log", "ok", "Run saved to SQLite")
        save_run(connection, str(path), invoice.vendor, str(invoice.total) if invoice.total else None,
                 decision, reason, trace)
        if invoice.vendor and invoice.invoice_no and invoice.total is not None:
            save_processed_invoice(
                connection, invoice.vendor, normalise_invoice_no(invoice.invoice_no),
                context.matched_po, str(invoice.total), decision,
            )

    return {"decision": decision, "reason": reason, "trace": trace, "invoice": invoice}