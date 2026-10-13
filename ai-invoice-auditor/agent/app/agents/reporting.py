"""Reporting Agent: JSON + HTML report, recommendation, persist to PostgreSQL."""
from ..config import load_rules


def decide(state: dict) -> str:
    p = load_rules()["validation_policies"]
    cur = (state.get("header") or {}).get("currency")
    if cur and cur not in load_rules()["accepted_currencies"]:
        return "reject"                                                  # invalid_currency_action
    if state.get("discrepancies") or state.get("missing_fields"):
        return "review"                                                  # flag / manual_review
    if state.get("translation_confidence", 1.0) >= p["auto_approve_confidence_threshold"]:
        return "approve"
    return "review"


def reporting_node(state: dict) -> dict:
    reco = decide(state)
    # TODO: build report dict (discrepancy summary, missing fields, translation confidence, recommendation);
    #       render Jinja2 HTML -> REPORTS_DIR/{invoice_id}.html and .json; INSERT outcome rows into audit.*.
    return {"recommendation": reco}
