from datetime import timedelta, timezone
from pathlib import Path


CONFIDENCE_CUTOFF = 0.8
TOLERANCE_PERCENT = 0.02
# Times are stored in UTC and shown to people in India Standard Time.
DISPLAY_TZ = timezone(timedelta(hours=5, minutes=30), "IST")
DB_PATH = Path(__file__).resolve().parent / "invoice_processor.db"
VENDORS_PATH = Path(__file__).resolve().parent / "data" / "vendors.csv"
POS_PATH = Path(__file__).resolve().parent / "data" / "pos.csv"