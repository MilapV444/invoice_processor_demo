"""Generate deterministic reference data and invoice PDFs for the demo."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
INVOICE_DIR = ROOT / "test_invoices"

VENDORS = [
    "Aarav Office Supplies Pvt Ltd",
    "Bharat IT Solutions Private Limited",
    "Cauvery Facility Services",
    "Deccan Industrial Components",
    "Narmada Logistics Services",
    "Saffron Cloud Technologies",
]

POS = [
    ("PO-4512", VENDORS[0], "240000", "A4 paper (100 boxes); Toner cartridges (20)",
     [("A4 paper", 100, 1200), ("Toner cartridges", 20, 6000)]),
    ("PO-4520", VENDORS[1], "180000", "Laptop docking stations (10); USB-C adapters (20)",
     [("Laptop docking stations", 10, 12000), ("USB-C adapters", 20, 3000)]),
    ("PO-4527", VENDORS[2], "95000", "Monthly office cleaning (3 months)",
     [("Monthly office cleaning", 3, 31666.67)]),
    ("PO-4531", VENDORS[3], "325000", "Steel fasteners (500 kg); Safety gloves (200 pairs)",
     [("Steel fasteners", 500, 500), ("Safety gloves", 200, 375)]),
    ("PO-4538", VENDORS[4], "125000", "Inter-city freight (5 trips)",
     [("Inter-city freight", 5, 25000)]),
    ("PO-4544", VENDORS[5], "210000", "Cloud support retainer (6 months)",
     [("Cloud support retainer", 6, 35000)]),
    ("PO-4550", VENDORS[0], "72000", "Printer maintenance (4 visits)",
     [("Printer maintenance", 4, 18000)]),
    ("PO-4556", VENDORS[2], "56000", "Pest control service (4 visits)",
     [("Pest control service", 4, 14000)]),
]


def write_reference_csvs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "vendors.csv").write_text(
        "vendor\n" + "\n".join(VENDORS) + "\n", encoding="utf-8"
    )
    rows = ["po_number,vendor,amount,line_items"]
    rows.extend(
        f'{po_number},{vendor},{amount},"{line_items}"'
        for po_number, vendor, amount, line_items, _ in POS
    )
    (DATA_DIR / "pos.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def pdf_bytes(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def text_pdf(lines: list[str]) -> bytes:
    content = "BT /F1 12 Tf 60 780 Td " + " ".join(
        f"({line.replace('(', '\\(').replace(')', '\\)')}) Tj 0 -24 Td" for line in lines
    ) + " ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream".encode(),
    ]
    return pdf_bytes(objects)


def scanned_pdf(path: Path, lines: list[str]) -> None:
    # Pillow is only needed to generate test data, not to run the app.
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    page = Image.new("L", (1240, 1754), 255)  # A4 at 150 dpi, greyscale
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=30)
    for row, line in enumerate(lines):
        draw.text((120, 150 + row * 55), line, fill=40, font=font)
    page = page.filter(ImageFilter.GaussianBlur(0.8))  # soft scan look, still readable

    # Smudge only the total amount, so the total is the field that cannot be read with confidence.
    label = "TOTAL INR "
    left = 120 + int(draw.textlength(label, font=font))
    top = 150 + (len(lines) - 1) * 55 - 10
    box = (left, top, left + 320, top + 55)
    page.paste(page.crop(box).filter(ImageFilter.GaussianBlur(6)), box)
    page.save(path, "PDF", resolution=150)


def draw_invoice(path: Path, invoice_no: str, vendor: str, po_ref: str | None,
                 total: float, items: list[tuple[str, int, float]], blur: bool = False) -> None:
    lines = ["TAX INVOICE", vendor, "India", f"Invoice No: {invoice_no}", "Date: 2026-09-20"]
    if po_ref:
        lines.append(f"PO Reference: {po_ref}")
    lines.extend(f"{description} | Qty {quantity} | INR {quantity * unit_price:,.2f}"
                 for description, quantity, unit_price in items)
    lines.append(f"TOTAL INR {total:,.2f}")
    path.parent.mkdir(exist_ok=True)
    if blur:
        scanned_pdf(path, lines)
    else:
        path.write_bytes(text_pdf(lines))


def generate_invoices() -> None:
    INVOICE_DIR.mkdir(exist_ok=True)
    draw_invoice(INVOICE_DIR / "happy_1.pdf", "INV-0001", VENDORS[0], "PO-4512", 120000,
                 [("A4 paper", 50, 1200), ("Toner cartridges", 10, 6000)])
    draw_invoice(INVOICE_DIR / "happy_2.pdf", "INV-0002", VENDORS[1], "PO-4520", 120000,
                 [("Laptop docking stations", 10, 12000)])
    draw_invoice(INVOICE_DIR / "happy_3.pdf", "INV-0003", VENDORS[4], "PO-4538", 50000,
                 [("Inter-city freight", 2, 25000)])

    draw_invoice(INVOICE_DIR / "ec1_scanned.pdf", "INV-SCAN-01", VENDORS[0], "PO-4512", 240000,
                 [("A4 paper", 100, 1200), ("Toner cartridges", 20, 6000)], blur=True)

    draw_invoice(INVOICE_DIR / "ec2_split_1.pdf", "INV-SPLIT-01", VENDORS[3], "PO-4531", 100000,
                 [("Steel fasteners", 200, 500)])
    draw_invoice(INVOICE_DIR / "ec2_split_2.pdf", "INV-SPLIT-02", VENDORS[3], "PO-4531", 100000,
                 [("Steel fasteners", 200, 500)])
    # 100k + 100k + 140k = 340k, above PO-4531's 325k x 1.02 = 331.5k limit.
    draw_invoice(INVOICE_DIR / "ec2_split_3.pdf", "INV-SPLIT-03", VENDORS[3], "PO-4531", 140000,
                 [("Steel fasteners", 100, 500), ("Safety gloves", 240, 375)])

    draw_invoice(INVOICE_DIR / "ec3_original.pdf", "INV-0045", VENDORS[5], "PO-4544", 35000,
                 [("Cloud support retainer", 1, 35000)])
    draw_invoice(INVOICE_DIR / "ec3_dupe.pdf", "INV-45", VENDORS[5], "PO-4544", 35000,
                 [("Cloud support retainer", 1, 35000)])
    draw_invoice(INVOICE_DIR / "ec4_no_po.pdf", "INV-INFER-01", VENDORS[0], None, 60000,
                 [("A4 paper", 50, 1200)])


if __name__ == "__main__":
    write_reference_csvs()
    generate_invoices()
    print(f"Generated reference data in {DATA_DIR}")
    print(f"Generated {len(list(INVOICE_DIR.glob('*.pdf')))} PDFs in {INVOICE_DIR}")