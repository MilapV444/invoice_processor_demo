import json
import tempfile
from pathlib import Path

import streamlit as st

from config import DB_PATH
from db import connect, reset, runs
from pipeline import process_invoice


SAMPLE_DIR = Path(__file__).resolve().parent / "test_invoices"
DECISIONS = ("APPROVE", "HOLD", "REJECT")
STAGE_LABELS = {
    "ingest": "Ingest",
    "extract": "Extract",
    "required_fields": "Validate: required fields",
    "confidence": "Validate: confidence",
    "approved_vendor": "Validate: approved vendor",
    "duplicate": "Check rules: duplicate",
    "po_match": "Match PO",
    "over_billing": "Check rules: over-billing",
    "all_pass": "Check rules: all pass",
    "decide": "Decide",
    "log": "Log",
}
STATUS_ICONS = {"ok": "✅", "warn": "⚠️"}
# Sidebar samples in demo order, with a one-line hint of what each one shows.
SAMPLES = {
    "happy_1.pdf": "Clean invoice that matches its PO → APPROVE",
    "happy_2.pdf": "Clean invoice that matches its PO → APPROVE",
    "happy_3.pdf": "Clean invoice that matches its PO → APPROVE",
    "ec1_scanned.pdf": "Scanned invoice with a blurry total → HOLD",
    "ec2_split_1.pdf": "PO split across 3 invoices, part 1 → APPROVE",
    "ec2_split_2.pdf": "PO split across 3 invoices, part 2 → APPROVE",
    "ec2_split_3.pdf": "PO split across 3 invoices, part 3 over-bills → HOLD",
    "ec3_original.pdf": "Original invoice INV-0045 → APPROVE",
    "ec3_dupe.pdf": "Same invoice re-sent as INV-45 → REJECT",
    "ec4_no_po.pdf": "No PO number, inferred from vendor + items → APPROVE",
}


def format_inr(amount: str | None) -> str:
    return f"{float(amount):,.2f}" if amount else "—"


def trace_line(entry: dict[str, str]) -> str:
    icon = STATUS_ICONS.get(entry["status"], "•")
    label = STAGE_LABELS.get(entry["stage"], entry["stage"])
    return f"{icon} **{label}** — {entry['detail']}"


def show_decision(decision: str, reason: str) -> None:
    show = {"APPROVE": st.success, "HOLD": st.warning, "REJECT": st.error}[decision]
    show(f"### {decision}\n{reason}")


def run_pipeline(pdf_path: Path, display_name: str) -> None:
    with st.status(f"Processing {display_name}…", expanded=True) as status:
        try:
            result = process_invoice(pdf_path, on_trace=lambda entry: st.markdown(trace_line(entry)))
        except RuntimeError as error:  # raised by extract.py when no API key is configured
            status.update(label="Could not process the invoice", state="error")
            st.session_state.pop("last_result", None)
            st.error(str(error))
            return
        except Exception:
            status.update(label="Could not process the invoice", state="error")
            st.session_state.pop("last_result", None)
            st.error("The invoice could not be read. Please check it is a valid PDF and try again.")
            return
        status.update(label=f"Processed {display_name}", state="complete")
    st.session_state["last_result"] = {
        "file": display_name,
        "decision": result["decision"],
        "reason": result["reason"],
        "trace": result["trace"],
    }


def process_tab(sample: Path | None) -> None:
    uploaded = st.file_uploader("Upload an invoice PDF", type="pdf")
    if uploaded and st.button("Process invoice", type="primary"):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / uploaded.name
            path.write_bytes(uploaded.getvalue())
            run_pipeline(path, uploaded.name)
    elif sample:
        run_pipeline(sample, sample.name)
    elif "last_result" in st.session_state:
        last = st.session_state["last_result"]
        st.caption(f"Last processed: {last['file']}")
        for entry in last["trace"]:
            st.markdown(trace_line(entry))

    if "last_result" in st.session_state:
        last = st.session_state["last_result"]
        show_decision(last["decision"], last["reason"])


def dashboard_tab() -> None:
    with connect(DB_PATH) as connection:
        rows = [dict(row) for row in runs(connection)]
    if not rows:
        st.info("No invoices processed yet.")
        return

    for column, decision in zip(st.columns(len(DECISIONS)), DECISIONS):
        column.metric(decision, sum(row["decision"] == decision for row in rows))

    chosen = st.multiselect("Filter by decision", DECISIONS, default=DECISIONS)
    shown = [row for row in rows if row["decision"] in chosen]
    table = [{
        "Run": row["run_id"],
        "File": Path(row["file"]).name,
        "Vendor": row["vendor"],
        "Total (INR)": format_inr(row["total"]),
        "Decision": row["decision"],
        "Reason": row["reason"],
        "Processed (UTC)": row["created_at"][:19].replace("T", " "),
    } for row in shown]
    selection = st.dataframe(table, hide_index=True, use_container_width=True,
                             on_select="rerun", selection_mode="single-row")

    if selection.selection.rows:
        run = shown[selection.selection.rows[0]]
        st.subheader(f"Trace for run {run['run_id']}: {Path(run['file']).name}")
        for entry in json.loads(run["trace_json"]):
            st.markdown(trace_line(entry))
    else:
        st.caption("Click a row to see its full stage-by-stage trace.")


st.set_page_config(page_title="Invoice → Decision", page_icon="🧾", layout="wide")
st.title("Invoice → Decision")
st.caption("Claude reads the invoice. Plain Python rules make the decision.")

sample = None
with st.sidebar:
    st.header("Demo controls")
    if st.button("Reset demo data"):
        reset(DB_PATH)
        st.session_state.pop("last_result", None)
        st.success("Run history cleared.")
    st.subheader("Sample invoices")
    st.caption("Hover a button to see what it demonstrates.")
    for name, hint in SAMPLES.items():
        if st.button(name, key=f"sample_{name}", help=hint, use_container_width=True):
            sample = SAMPLE_DIR / name

process, dashboard = st.tabs(["Process invoice", "Dashboard"])
with process:
    process_tab(sample)
with dashboard:
    dashboard_tab()
