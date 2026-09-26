import sys
from pathlib import Path

from config import DB_PATH
from db import reset
from pipeline import process_invoice


INVOICE_DIR = Path(__file__).resolve().parent / "test_invoices"

TEST_CASES = [
    ("happy_1.pdf", "APPROVE", "within tolerance"),
    ("ec1_scanned.pdf", "HOLD", "Low confidence"),
    ("ec2_split_1.pdf", "APPROVE", "within tolerance"),
    ("ec2_split_2.pdf", "APPROVE", "within tolerance"),
    ("ec2_split_3.pdf", "HOLD", "over-billed"),
    ("ec3_original.pdf", "APPROVE", "within tolerance"),
    ("ec3_dupe.pdf", "REJECT", "Duplicate"),
    ("ec4_no_po.pdf", "APPROVE", "PO inferred"),
]


def run_once() -> int:
    reset(DB_PATH)
    failures = 0
    for filename, expected_decision, expected_reason in TEST_CASES:
        try:
            result = process_invoice(INVOICE_DIR / filename)
        except Exception as error:
            failures += 1
            print(f"FAIL {filename}: {type(error).__name__}: {error}")
            continue
        decision = result["decision"]
        reason = result["reason"]
        if decision != expected_decision or expected_reason.lower() not in reason.lower():
            failures += 1
            print(f"FAIL {filename}: expected {expected_decision} / {expected_reason!r}, "
                  f"got {decision} / {reason!r}")
        else:
            print(f"PASS {filename}: {decision} - {reason}")
    return failures


if __name__ == "__main__":
    failures = run_once()
    if failures:
        print(f"{failures} of {len(TEST_CASES)} invoice tests failed.")
        sys.exit(1)
    print("All invoice tests passed.")
