import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Connection(sqlite3.Connection):
    def __exit__(self, *args: object) -> None:
        try:
            super().__exit__(*args)
        finally:
            self.close()


def connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, factory=Connection)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file TEXT NOT NULL,
            vendor TEXT,
            total TEXT,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            trace_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS processed_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            invoice_no TEXT,
            normalised_invoice_no TEXT NOT NULL,
            po_number TEXT,
            total TEXT NOT NULL,
            decision TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );
    """)
    # Upgrade databases created before invoice_no was stored as printed.
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(processed_invoices)")}
    if "invoice_no" not in columns:
        connection.execute("ALTER TABLE processed_invoices ADD COLUMN invoice_no TEXT")
    return connection


def reset(db_path: str | Path) -> None:
    with connect(db_path) as connection:
        connection.executescript("DELETE FROM runs; DELETE FROM processed_invoices;")


def processed_invoices(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM processed_invoices ORDER BY processed_at"
    ).fetchall()


def runs(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute("SELECT * FROM runs ORDER BY run_id DESC").fetchall()


def save_run(connection: sqlite3.Connection, file: str, vendor: str | None,
             total: str | None, decision: str, reason: str,
             trace: list[dict[str, str]]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        "INSERT INTO runs (file, vendor, total, decision, reason, trace_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (file, vendor, total, decision, reason, json.dumps(trace), now),
    )
    connection.commit()


def save_processed_invoice(connection: sqlite3.Connection, vendor: str, invoice_no: str,
                           normalised_invoice_no: str, po_number: str | None,
                           total: str, decision: str) -> None:
    connection.execute(
        "INSERT INTO processed_invoices "
        "(vendor, invoice_no, normalised_invoice_no, po_number, total, decision, processed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (vendor, invoice_no, normalised_invoice_no, po_number, total, decision,
         datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()