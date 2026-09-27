import html
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from config import DB_PATH, DISPLAY_TZ
from db import connect, reset, runs
from pipeline import process_invoice


ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "test_invoices"
DECISIONS = ("APPROVE", "HOLD", "REJECT")
PAGE_SIZE = 10
STAGE_LABELS = {
    "ingest": "Ingest",
    "extract": "Extract",
    "required_fields": "Validate · required fields",
    "confidence": "Validate · confidence",
    "approved_vendor": "Validate · approved vendor",
    "duplicate": "Check · duplicate",
    "po_match": "Match PO",
    "over_billing": "Check · over-billing",
    "all_pass": "Check · all pass",
    "decide": "Decide",
    "log": "Log",
}
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
FEED_HEAD = ('<div class="feed-head"><div class="feed-title"><span class="dot"></span>Decision feed</div>'
             '<span class="mono">Live</span></div><div class="feed-body">')
FEED_FOOT = '</div><div class="mono foot">Claude extracts · Python rules decide</div>'
IDLE_BUBBLE = ('<div class="msg"><div class="bubble sys">Upload an invoice or pick a sample. '
               'Every check appears here as it runs, then the decision and its reason.</div></div>')
TYPING_BUBBLE = ('<div class="msg"><div class="bubble sys"><span class="stage">Extract</span>'
                 'Claude is reading the invoice <span class="typing"><i></i><i></i><i></i></span></div></div>')


# Everything shown in HTML is escaped: vendor names and reasons come from invoice content.
def esc(value: object) -> str:
    return html.escape(str(value))


def html_block(markup: str, target=st) -> None:
    # The "ui" wrapper lets styles.css cancel Streamlit's negative text margin for our own HTML.
    target.markdown(f'<div class="ui">{markup}</div>', unsafe_allow_html=True)


def format_inr(amount: str | None) -> str:
    return f"{float(amount):,.2f}" if amount else "—"


def clock(iso_time: str | None = None) -> str:
    moment = datetime.fromisoformat(iso_time) if iso_time else datetime.now(timezone.utc)
    return moment.astimezone(DISPLAY_TZ).strftime("%I:%M %p %Z").lstrip("0")


def load_runs() -> list[dict]:
    with connect(DB_PATH) as connection:
        return [dict(row) for row in runs(connection)]


# ---- HTML pieces -----------------------------------------------------------------

def header_html(rows: list[dict]) -> str:
    holds = sum(row["decision"] == "HOLD" for row in rows)
    return (
        '<div class="hd"><div class="hd-brand"><div class="logo"><span>I</span></div>'
        '<div><div class="brand-name">Invoice → Decision</div>'
        '<div class="mono">CLAUDE READS · RULES DECIDE</div></div></div>'
        f'<span class="mono hd-stats"><b>{len(rows)}</b> processed · <b>{holds}</b> need review</span></div>'
    )


def card_head(label: str, title: str, right: str = "") -> str:
    return (f'<div class="card-head"><div><div class="mono">{label}</div>'
            f'<div class="card-title">{title}</div></div>{right}</div>')


def stage_bubble(entry: dict[str, str], decision: str | None = None) -> str:
    label = STAGE_LABELS.get(entry["stage"], entry["stage"])
    if entry["status"] == "ok":
        return (f'<div class="msg"><div class="bubble sys"><span class="stage">✓ {esc(label)}</span>'
                f'{esc(entry["detail"])}</div></div>')
    # The one check that failed is shown in the colour of the outcome it caused,
    # so it stands out: amber for HOLD, red for REJECT.
    outcome = f" → {decision}" if decision else ""
    tone = (decision or "hold").lower()
    return (f'<div class="msg"><div class="bubble alert {tone}"><span class="stage">'
            f'{"✕" if tone == "reject" else "!"} {esc(label)} <b class="failed">FAILED{esc(outcome)}</b></span>'
            f'{esc(entry["detail"])}</div></div>')


def trace_bubbles(trace: list[dict[str, str]], decision: str | None = None) -> list[str]:
    return [stage_bubble(entry, decision) for entry in trace]


def user_bubble(file_name: str, time: str) -> str:
    return (f'<div class="msg me"><div class="bubble user">Process <b>{esc(file_name)}</b></div>'
            f'<span class="time">{esc(time)}</span></div>')


def decision_bubble(decision: str, reason: str, time: str) -> str:
    return (f'<div class="msg"><div class="bubble decision {decision.lower()}">'
            f'<span class="verdict">{esc(decision)}</span>{esc(reason)}</div>'
            f'<span class="time">{esc(time)}</span></div>')


def error_bubble(message: str) -> str:
    return (f'<div class="msg"><div class="bubble decision reject">'
            f'<span class="verdict">Couldn\'t process</span>{esc(message)}</div></div>')


def queue_rows_html(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty">No invoices yet. Upload one, or pick a sample from the sidebar.</div>'
    items = []
    for index, row in enumerate(rows):
        decision = row["decision"].lower()
        title = f'{esc(Path(row["file"]).name)} · {esc(row["vendor"] or "Unknown vendor")}'
        sub = f'INR {format_inr(row["total"])} · {esc(row["reason"])}'
        items.append(
            f'<div class="row" style="animation-delay:{min(index, 5) * 60 + 120}ms">'
            f'<div class="tile {decision}">PDF</div>'
            f'<div class="row-main"><div class="row-title">{title}</div><div class="row-sub">{sub}</div></div>'
            f'<span class="pill {decision}">{esc(row["decision"])}</span>'
            f'<span class="mono when">{clock(row["created_at"])}</span></div>'
        )
    return "".join(items)


# ---- Processing ------------------------------------------------------------------

def show_feed(slot, bubbles: list[str], extra: str = "") -> None:
    # The whole feed is one HTML block that is redrawn each time, so a new run
    # replaces everything from the previous invoice instead of leaving it behind.
    slot.markdown(f'<div class="ui">{FEED_HEAD}{"".join(bubbles)}{extra}{FEED_FOOT}</div>',
                  unsafe_allow_html=True)


def run_pipeline(slot, pdf_path: Path, display_name: str) -> None:
    started = clock()
    opening = [user_bubble(display_name, started)]
    trace: list[dict[str, str]] = []
    show_feed(slot, opening)

    def on_trace(entry: dict[str, str]) -> None:
        trace.append(entry)
        # Extraction is the slow step, so show a typing indicator right after ingest.
        show_feed(slot, opening + trace_bubbles(trace), TYPING_BUBBLE if entry["stage"] == "ingest" else "")

    try:
        result = process_invoice(pdf_path, on_trace=on_trace)
    except RuntimeError as error:  # raised by extract.py when no API key is configured
        message = str(error)
    except Exception:
        message = "The invoice could not be read. Please check it is a valid PDF and try again."
    else:
        message = None
    if message:
        st.session_state.pop("last_result", None)
        show_feed(slot, opening + trace_bubbles(trace) + [error_bubble(message)])
        return

    finished = clock()
    # Final redraw now that the decision is known, so the failed check gets its outcome colour.
    show_feed(slot, opening + trace_bubbles(trace, result["decision"])
              + [decision_bubble(result["decision"], result["reason"], finished)])
    st.session_state["queue_page"] = 0  # jump back to the newest invoices
    st.session_state["last_result"] = {
        "file": display_name,
        "decision": result["decision"],
        "reason": result["reason"],
        "trace": result["trace"],
        "started": started,
        "finished": finished,
    }


def replay_feed(slot, last: dict) -> None:
    show_feed(slot, [user_bubble(last["file"], last["started"])]
              + trace_bubbles(last["trace"], last["decision"])
              + [decision_bubble(last["decision"], last["reason"], last["finished"])])


# ---- Tabs --------------------------------------------------------------------------

def turn_page(step: int) -> None:
    st.session_state["queue_page"] = st.session_state.get("queue_page", 0) + step


def queue_card(rows: list[dict]) -> None:
    pages = max(1, -(-len(rows) // PAGE_SIZE))  # ceiling division
    page = min(max(st.session_state.get("queue_page", 0), 0), pages - 1)
    shown = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    first, last = page * PAGE_SIZE + 1, page * PAGE_SIZE + len(shown)
    count = f'{first}–{last} of {len(rows)}' if rows else "0 invoices"
    html_block(card_head("(b) QUEUE", "Processed invoices",
                         f'<span class="mono">Newest first<span class="sort">{count}</span></span>')
               + queue_rows_html(shown))
    if pages > 1:
        with st.container(key="queue_pager"):
            newer, label, older = st.columns([1, 2, 1], vertical_alignment="center")
            newer.button("← Newer", key="page_newer", disabled=page == 0,
                         on_click=turn_page, args=(-1,), use_container_width=True)
            html_block(f'<div class="mono pager-label">Page {page + 1} of {pages}</div>', label)
            older.button("Older →", key="page_older", disabled=page == pages - 1,
                         on_click=turn_page, args=(1,), use_container_width=True)


def workspace_tab(sample: Path | None) -> None:
    left, right = st.columns([7, 5], gap="large")
    with left:
        with st.container(key="upload_card"):
            html_block(card_head("(a) WORKSPACE", "Process an invoice",
                                 '<span class="mono">One PDF at a time</span>'))
            html_block('<div class="upload-head"><div class="upload-icon"><div></div></div>'
                       '<div><div class="card-title">Upload an invoice</div>'
                       '<div class="card-sub">Drop a PDF or a scan. Claude reads it, then fixed rules decide.'
                       '</div></div></div>')
            uploaded = st.file_uploader("Upload an invoice PDF", type="pdf", label_visibility="collapsed")
            clicked = st.button("Process invoice", type="primary", disabled=uploaded is None)
        queue = st.container(key="queue_card")

    with right:
        with st.container(key="feed_card"):
            feed = st.empty()
            if uploaded and clicked:
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / uploaded.name
                    path.write_bytes(uploaded.getvalue())
                    run_pipeline(feed, path, uploaded.name)
            elif sample:
                run_pipeline(feed, sample, sample.name)
            elif "last_result" in st.session_state:
                replay_feed(feed, st.session_state["last_result"])
            else:
                show_feed(feed, [IDLE_BUBBLE])

    with queue:
        queue_card(load_runs())


def dashboard_tab() -> None:
    rows = load_runs()
    html_block('<div class="page-head"><div><div class="mono">(c) HISTORY</div>'
               '<div class="page-title">All runs</div></div></div>')
    if not rows:
        st.info("No invoices processed yet.")
        return

    for column, decision in zip(st.columns(len(DECISIONS)), DECISIONS):
        with column.container(key=f"metric_{decision.lower()}"):
            st.metric(decision, sum(row["decision"] == decision for row in rows))

    chosen = st.multiselect("Filter by decision", DECISIONS, default=DECISIONS)
    shown = [row for row in rows if row["decision"] in chosen]
    table = [{
        "Run": row["run_id"],
        "File": Path(row["file"]).name,
        "Vendor": row["vendor"],
        "Total (INR)": format_inr(row["total"]),
        "Decision": row["decision"],
        "Reason": row["reason"],
        "Processed (IST)": clock(row["created_at"]),
    } for row in shown]
    selection = st.dataframe(table, hide_index=True, use_container_width=True,
                             on_select="rerun", selection_mode="single-row")

    if selection.selection.rows:
        run = shown[selection.selection.rows[0]]
        with st.container(key="trace_card"):
            bubbles = (trace_bubbles(json.loads(run["trace_json"]), run["decision"])
                       + [decision_bubble(run["decision"], run["reason"], clock(run["created_at"]))])
            html_block(f'<div class="feed-head"><div class="feed-title"><span class="dot"></span>'
                       f'Trace · run {run["run_id"]}</div><span class="mono">{esc(Path(run["file"]).name)}</span></div>'
                       f'<div class="feed-body">{"".join(bubbles)}</div>')
    else:
        st.caption("Click a row to see its full stage-by-stage trace.")


# ---- Page --------------------------------------------------------------------------

st.set_page_config(page_title="Invoice → Decision", page_icon="🧾", layout="wide")
st.markdown(f"<style>{(ROOT / 'styles.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
header = st.empty()

sample = None
with st.sidebar:
    html_block('<div class="side-label">DEMO CONTROLS</div>')
    if st.button("Reset demo data", use_container_width=True):
        reset(DB_PATH)
        st.session_state.pop("last_result", None)
        st.session_state["queue_page"] = 0
        st.toast("Run history cleared.")
    html_block('<div class="side-label">SAMPLE INVOICES · HOVER FOR HINTS</div>')
    for name, hint in SAMPLES.items():
        if st.button(name, key=f"sample_{name}", help=hint, use_container_width=True):
            sample = SAMPLE_DIR / name

workspace, dashboard = st.tabs(["Workspace", "Dashboard"])
with workspace:
    workspace_tab(sample)
with dashboard:
    dashboard_tab()

# Filled last so the counts include an invoice processed in this run.
html_block(header_html(load_runs()), header)
