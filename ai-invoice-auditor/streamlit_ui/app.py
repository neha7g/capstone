"""Human-in-the-loop dashboard for the AI Invoice Auditor.

Service boundaries (see architecture):
  * READS  the `audit` schema straight from PostgreSQL (never the `erp` schema).
  * WRITES nothing itself: corrections and re-validation go through the agent's HTTP API,
    because the agent is the only service that writes application data.
"""
import os
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import psycopg
import streamlit as st
import streamlit.components.v1 as components
from psycopg.rows import dict_row

# ----------------------------------------------------------------------------- config
try:
    DSN = (f"host={os.environ.get('POSTGRES_HOST', 'postgres')} port={os.environ.get('POSTGRES_PORT', '5432')} "
           f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
           f"password={os.environ['POSTGRES_PASSWORD']}")
except KeyError as e:                                   # fail clearly instead of half-working
    st.error(f"Dashboard is not configured: missing environment variable {e}.")
    st.stop()
AGENT_URL = os.environ.get("AGENT_URL", "http://agent:8000")
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/outputs/reports"))

REQUIRED_HEADER = {"invoice_number": "Invoice number", "invoice_date": "Invoice date",
                   "currency": "Currency", "total_amount": "Total amount"}
HEADER_FIELDS = {"invoice_number": "Invoice number", "invoice_date": "Invoice date (YYYY-MM-DD)",
                 "vendor_name": "Vendor name", "po_number": "PO number", "currency": "Currency (e.g. USD)",
                 "total_amount": "Total amount", "tax_amount": "Tax amount"}
LINE_FIELDS = {"item_code": "Item code", "quantity": "Quantity", "unit_price": "Unit price"}
BADGE = {"approve": "🟢 Approve", "review": "🟠 Needs review", "reject": "🔴 Reject", None: "⚪ Pending"}

st.set_page_config(page_title="Invoice Auditor", page_icon="🧾", layout="wide")


# ----------------------------------------------------------------------------- data access
def fetch(sql: str, params: tuple = ()) -> list[dict]:
    try:
        with psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5) as c:
            return c.execute(sql, params).fetchall()
    except psycopg.Error as exc:
        st.error(f"Could not read the audit database: {exc}")
        st.stop()


def agent_call(method: str, path: str, timeout: float = 30, **kw):
    """Returns (ok, payload_or_message)."""
    try:
        r = httpx.request(method, f"{AGENT_URL}{path}", timeout=timeout, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            return False, f"The agent returned an error ({r.status_code}): {detail}"
        return True, r.json()
    except httpx.HTTPError as exc:
        return False, f"Could not reach the agent service: {exc}"


def money(v, cur) -> str:
    return "—" if v is None else f"{float(v):,.2f} {cur or ''}".strip()


def pct(v) -> str:
    return "—" if v is None else f"{float(v) * 100:.0f}%"


def invoice_label(r: dict) -> str:
    return f"{r['invoice_number'] or '(no number)'} · {r['vendor_name'] or 'unknown vendor'} · " \
           f"{(r['recommendation'] or r['processing_status'] or 'pending')}"


def load_invoices() -> list[dict]:
    return fetch("""
        SELECT a.*, (SELECT count(*) FROM audit.discrepancies d WHERE d.invoice_id = a.invoice_id) AS n_disc
        FROM audit.invoice_audit a ORDER BY a.processed_at DESC""")


def effective_values(inv: dict, lines: list[dict], feedback: list[dict]) -> dict:
    """Current value of every correctable field = original extraction overlaid by the latest correction."""
    vals = {k: inv.get(k) for k in HEADER_FIELDS}
    for l in lines:
        for f in LINE_FIELDS:
            vals[f"line[{l['line_number']}].{f}"] = l.get(f if f != "quantity" else "quantity")
    for fb in sorted(feedback, key=lambda x: x["id"]):        # oldest -> newest, newest wins
        vals[fb["field_name"]] = fb["corrected_value"]
    return vals


# ----------------------------------------------------------------------------- header + KPIs
st.title("🧾 Invoice Auditor")
st.caption("Review what the system found, fix anything it read wrongly, and ask questions about your invoices.")

invoices = load_invoices()
with st.sidebar:
    st.header("Filters")
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()
    status_f = st.multiselect("Recommendation", ["approve", "review", "reject"])
    search = st.text_input("Search vendor / invoice number")
    only_issues = st.checkbox("Only invoices with discrepancies or errors")
    st.divider()
    st.caption(f"Agent service: `{AGENT_URL}`")

visible = [r for r in invoices
           if (not status_f or r["recommendation"] in status_f)
           and (not search or search.lower() in f"{r['vendor_name']} {r['invoice_number']}".lower())
           and (not only_issues or r["n_disc"] or r["processing_status"] == "error")]

k = st.columns(5)
k[0].metric("Invoices", len(invoices))
k[1].metric("Approved", sum(r["recommendation"] == "approve" for r in invoices))
k[2].metric("Needs review", sum(r["recommendation"] == "review" for r in invoices))
k[3].metric("Rejected", sum(r["recommendation"] == "reject" for r in invoices))
k[4].metric("Failed to process", sum(r["processing_status"] == "error" for r in invoices))

tab_reports, tab_correct, tab_ask = st.tabs(["📋 Reports", "✏️ Correct & re-validate", "💬 Ask a question"])

# ----------------------------------------------------------------------------- tab 1: reports
with tab_reports:
    if not invoices:
        st.info("No invoices have been processed yet. Drop invoice files into the incoming folder and they will appear here.")
    elif not visible:
        st.warning("No invoices match the current filters.")
    else:
        st.dataframe(pd.DataFrame([{
            "Invoice": r["invoice_number"], "Vendor": r["vendor_name"], "PO": r["po_number"],
            "Total": money(r["total_amount"], r["currency"]), "Decision": BADGE.get(r["recommendation"], "⚪ Pending"),
            "Issues": r["n_disc"], "Translation confidence": pct(r["translation_confidence"]),
            "Status": r["processing_status"], "Processed": r["processed_at"]} for r in visible]),
            use_container_width=True, hide_index=True)

        by_id = {r["invoice_id"]: r for r in visible}
        sel = st.selectbox("Open an invoice", list(by_id), format_func=lambda i: invoice_label(by_id[i]), key="rep_sel")
        inv = by_id[sel]
        lines = fetch("SELECT * FROM audit.invoice_line_items WHERE invoice_id=%s ORDER BY line_number", (sel,))
        discs = fetch("SELECT * FROM audit.discrepancies WHERE invoice_id=%s ORDER BY id", (sel,))
        fbs = fetch("SELECT * FROM audit.human_feedback WHERE invoice_id=%s ORDER BY id DESC", (sel,))

        st.subheader(f"{inv['invoice_number'] or 'Invoice without a number'} — {inv['vendor_name'] or 'unknown vendor'}")
        if inv["processing_status"] == "error":
            st.error(f"This file could not be processed: {inv['error_message']}")

        c = st.columns(4)
        c[0].metric("Decision", BADGE.get(inv["recommendation"], "⚪ Pending"))
        c[1].metric("Total", money(inv["total_amount"], inv["currency"]))
        c[2].metric("Language", (inv["source_language"] or "—").upper())
        c[3].metric("Translation confidence", pct(inv["translation_confidence"]))

        report = inv.get("report_json") or {}
        missing = report.get("missing_fields")
        if missing is None:
            missing = [lbl for f, lbl in REQUIRED_HEADER.items() if inv.get(f) in (None, "")]
        if missing:
            st.warning("Missing information: " + ", ".join(missing))

        st.markdown("**Discrepancies against the purchase order**")
        if discs:
            st.dataframe(pd.DataFrame([{
                "Field": d["field_name"], "On invoice": d["invoice_value"], "In ERP": d["erp_value"],
                "Difference %": None if d["deviation_pct"] is None else round(float(d["deviation_pct"]), 2),
                "Severity": d["severity"]} for d in discs]), use_container_width=True, hide_index=True)
        else:
            st.success("No discrepancies recorded.")

        st.markdown("**Line items**")
        if lines:
            st.dataframe(pd.DataFrame([{
                "#": l["line_number"], "Item code": l["item_code"], "Description": l["description"],
                "Qty": l["quantity"], "Unit price": l["unit_price"], "Line total": l["line_total"]} for l in lines]),
                use_container_width=True, hide_index=True)
        else:
            st.caption("No line items were extracted.")

        html_file = REPORTS_DIR / f"{sel}.html"
        with st.expander("Full audit report"):
            if html_file.exists():
                components.html(html_file.read_text(), height=600, scrolling=True)
            else:
                st.caption("No report file available yet.")
        with st.expander("Text read from the document"):
            st.text(inv["raw_extracted_text"] or "—")
            if inv["translated_text"] and inv["source_language"] not in (None, "en"):
                st.markdown("**English translation**")
                st.text(inv["translated_text"])
        if fbs:
            with st.expander(f"Correction history ({len(fbs)})"):
                st.dataframe(pd.DataFrame([{
                    "When": f["corrected_at"], "By": f["corrected_by"], "Field": f["field_name"],
                    "From": f["original_value"], "To": f["corrected_value"],
                    "Re-validated": "yes" if f["revalidated"] else "not yet"} for f in fbs]),
                    use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------- tab 2: corrections
with tab_correct:
    st.write("If the system read a value wrongly, enter the right one. Your correction is **saved alongside** the "
             "original (the original is never overwritten) and the invoice can then be checked again.")
    if not invoices:
        st.info("Nothing to correct yet.")
    else:
        by_id = {r["invoice_id"]: r for r in invoices}
        sel = st.selectbox("Invoice", list(by_id), format_func=lambda i: invoice_label(by_id[i]), key="cor_sel")
        inv = by_id[sel]
        lines = fetch("SELECT * FROM audit.invoice_line_items WHERE invoice_id=%s ORDER BY line_number", (sel,))
        fbs = fetch("SELECT * FROM audit.human_feedback WHERE invoice_id=%s ORDER BY id", (sel,))
        current = effective_values(inv, lines, fbs)

        labels = dict(HEADER_FIELDS)
        for l in lines:
            for f, lbl in LINE_FIELDS.items():
                labels[f"line[{l['line_number']}].{f}"] = f"Line {l['line_number']} — {lbl}"

        with st.form("correction", clear_on_submit=True):
            field = st.selectbox("What needs correcting?", list(labels), format_func=labels.get)
            st.caption(f"Current value: **{current.get(field) if current.get(field) not in (None, '') else '(empty)'}**")
            new_val = st.text_input("Correct value")
            who = st.text_input("Your name", help="Recorded with the correction for the audit trail.")
            recheck = st.checkbox("Re-validate this invoice after saving", value=True)
            submitted = st.form_submit_button("Save correction", type="primary")

        if submitted:
            err = None
            if not who.strip():
                err = "Please enter your name."
            elif new_val.strip() == "":
                err = "Please enter the corrected value."
            elif str(current.get(field)) == new_val.strip():
                err = "That is already the current value."
            elif field == "invoice_date":
                try:
                    date.fromisoformat(new_val.strip())
                except ValueError:
                    err = "Dates must look like 2025-03-14."
            elif field in ("total_amount", "tax_amount") or field.endswith((".quantity", ".unit_price")):
                try:
                    float(new_val.replace(",", ""))
                except ValueError:
                    err = "That field needs a number."
            if err:
                st.error(err)
            else:
                ok, res = agent_call("POST", "/feedback", json={
                    "invoice_id": sel, "field_name": field,
                    "original_value": None if current.get(field) is None else str(current.get(field)),
                    "corrected_value": new_val.strip(), "corrected_by": who.strip()})
                if not ok:
                    st.error(res)
                else:
                    st.success("Correction saved.")
                    if recheck:
                        ok2, res2 = agent_call("POST", f"/revalidate/{sel}", timeout=120)
                        st.success("Invoice re-validated.") if ok2 else st.warning(
                            f"Saved, but re-validation did not run: {res2}")

        if st.button("Re-validate this invoice now"):
            ok, res = agent_call("POST", f"/revalidate/{sel}", timeout=120)
            st.success("Invoice re-validated. Refresh to see the new result.") if ok else st.error(res)

# ----------------------------------------------------------------------------- tab 3: ask
with tab_ask:
    st.write("Ask in plain language, for example *“Why was invoice INV-1001 flagged?”* or "
             "*“Which vendors have price differences?”*")
    scope_opts = {"All invoices": None, **{invoice_label(r): r["invoice_id"] for r in invoices}}
    scope = st.selectbox("Search in", list(scope_opts))
    history = st.session_state.setdefault("chat", [])
    for m in history:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("meta"):
                st.caption(m["meta"])
    q = st.chat_input("Type your question")
    if q:
        history.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Looking through the invoices…"):
                ok, res = agent_call("POST", "/query", timeout=180,
                                     json={"question": q, "invoice_id": scope_opts[scope]})
            if not ok:
                answer, meta = f"Sorry, I couldn't answer that. {res}", None
            else:
                answer = res.get("answer", "No answer returned.")
                s = res.get("scores") or {}
                meta = ("Answer quality — " + ", ".join(f"{k.replace('_', ' ')} {float(v):.2f}" for k, v in s.items())
                        if s else None)
                if res.get("sources"):
                    meta = (meta + " · " if meta else "") + f"{len(res['sources'])} source passages"
            st.markdown(answer)
            if meta:
                st.caption(meta)
        history.append({"role": "assistant", "content": answer, "meta": meta})
    if history and st.button("Clear conversation"):
        st.session_state["chat"] = []
        st.rerun()