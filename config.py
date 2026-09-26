from pathlib import Path


CONFIDENCE_CUTOFF = 0.8
TOLERANCE_PERCENT = 0.02
DB_PATH = Path(__file__).resolve().parent / "invoice_processor.db"
VENDORS_PATH = Path(__file__).resolve().parent / "data" / "vendors.csv"
POS_PATH = Path(__file__).resolve().parent / "data" / "pos.csv"