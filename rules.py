import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable

from config import CONFIDENCE_CUTOFF, DISPLAY_TZ, TOLERANCE_PERCENT
from models import Invoice


@dataclass
class RuleContext:
    invoice: Invoice
    vendors: set[str]
    pos: dict[str, dict[str, object]]
    processed: list[sqlite3.Row]
    matched_po: str | None = None
    po_inferred: bool = False
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleResult:
    passed: bool
    outcome: str | None
    reason: str


def normalise_invoice_no(invoice_no: str) -> str:
    # Drop leading zeros per number first, so "INV-0045" and "INV-45" match.
    without_zeros = re.sub(r"\d+", lambda match: str(int(match.group())), invoice_no.lower())
    return re.sub(r"[^a-z0-9]", "", without_zeros)


COMPANY_WORDS = {"private": "pvt", "limited": "ltd", "and": "&"}


def normalise_vendor(vendor: str) -> str:
    # "Bharat IT Solutions Pvt. Ltd." and "Bharat IT Solutions Private Limited" match.
    words = re.sub(r"[^a-z0-9&]+", " ", vendor.lower()).split()
    return " ".join(COMPANY_WORDS.get(word, word) for word in words)


def normalise_po(po_ref: str) -> str:
    # "PO-4512", "PO 4512", "po#4512" and "4512" all become "4512".
    return re.sub(r"[^a-z0-9]", "", po_ref.lower()).removeprefix("po")


def same_vendor(first: str | None, second: str | None) -> bool:
    return bool(first and second) and normalise_vendor(first) == normalise_vendor(second)


def required_fields(context: RuleContext) -> RuleResult:
    missing = [name for name, value in (
        ("invoice number", context.invoice.invoice_no),
        ("vendor", context.invoice.vendor),
        ("total", context.invoice.total),
    ) if not value]
    if missing:
        return RuleResult(False, "HOLD", f"Missing: {', '.join(missing)}")
    return RuleResult(True, None, "Required fields present")


def confidence(context: RuleContext) -> RuleResult:
    labels = {"vendor": "vendor", "invoice_no": "invoice number", "total": "total"}
    for field_name, label in labels.items():
        if context.invoice.confidence[field_name] < CONFIDENCE_CUTOFF:
            return RuleResult(
                False, "HOLD",
                f"Low confidence reading {label}, please verify",
            )
    return RuleResult(True, None, "Key fields meet confidence threshold")


def approved_vendor(context: RuleContext) -> RuleResult:
    if not any(same_vendor(context.invoice.vendor, vendor) for vendor in context.vendors):
        return RuleResult(False, "REJECT", "Vendor not on approved list")
    return RuleResult(True, None, "Vendor is on the approved list")


def duplicate(context: RuleContext) -> RuleResult:
    invoice_no = normalise_invoice_no(context.invoice.invoice_no or "")
    for row in context.processed:
        if (same_vendor(row["vendor"], context.invoice.vendor)
                and row["normalised_invoice_no"] == invoice_no
                and Decimal(row["total"]) == context.invoice.total):
            original = row["invoice_no"] or row["normalised_invoice_no"]
            when = datetime.fromisoformat(row["processed_at"]).astimezone(DISPLAY_TZ).strftime("%d %b %Y at %H:%M %Z")
            return RuleResult(
                False, "REJECT",
                f"Duplicate of invoice {original}, already processed on {when}",
            )
    return RuleResult(True, None, "No matching processed invoice found")


def po_match(context: RuleContext) -> RuleResult:
    if context.invoice.po_ref:
        for po_number in context.pos:
            if normalise_po(po_number) == normalise_po(context.invoice.po_ref):
                context.matched_po = po_number
                return RuleResult(True, None, f"Matched PO {po_number}")

    # Infer only from vendor AND line items: every invoice line must appear on the PO.
    items = context.invoice.line_items
    candidates = [
        po_number for po_number, po in context.pos.items()
        if items
        and same_vendor(po["vendor"], context.invoice.vendor)
        and all(
            any(item.description.lower() in po_item.lower() for po_item in po["line_items"])
            for item in items
        )
    ]
    if len(candidates) == 1:
        context.matched_po = candidates[0]
        context.po_inferred = True
        return RuleResult(
            True, None,
            f"PO inferred: {candidates[0]} (vendor + {len(items)}/{len(items)} line items)",
        )
    return RuleResult(False, "HOLD", "No matching PO found")


def over_billing(context: RuleContext) -> RuleResult:
    po = context.pos[context.matched_po]
    billed = sum(
        (Decimal(row["total"]) for row in context.processed
         if row["po_number"] == context.matched_po and row["decision"] == "APPROVE"),
        Decimal("0"),
    )
    allowed = Decimal(str(po["amount"])) * (Decimal("1") + Decimal(str(TOLERANCE_PERCENT)))
    projected = billed + context.invoice.total
    if projected > allowed:
        excess = projected - allowed
        return RuleResult(
            False, "HOLD",
            f"PO {context.matched_po} would be over-billed by INR {excess:,.2f}",
        )
    return RuleResult(True, None, f"PO {context.matched_po} is within tolerance")


def all_pass(context: RuleContext) -> RuleResult:
    note = " (PO inferred)" if context.po_inferred else ""
    return RuleResult(True, "APPROVE", f"Matches PO {context.matched_po} within tolerance{note}")


RULES: list[Callable[[RuleContext], RuleResult]] = [
    required_fields,
    confidence,
    approved_vendor,
    duplicate,
    po_match,
    over_billing,
    all_pass,
]