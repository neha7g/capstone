"""Business Validation Agent: invoice vs PO via mock-erp HTTP API; one discrepancy row per mismatched field."""
from ..config import load_rules
from ..services import erp_client


def pct_dev(inv: float, erp: float) -> float:
    return 0.0 if erp == 0 else abs(inv - erp) / abs(erp) * 100


def business_validation_node(state: dict) -> dict:
    rules, tol = load_rules(), load_rules()["tolerances"]
    po = erp_client.get_po(state["header"].get("po_number", ""))
    discrepancies: list[dict] = []
    if po is None:
        discrepancies.append({"field_name": "po_number", "invoice_value": state["header"].get("po_number"),
                              "erp_value": None, "deviation_pct": None, "severity": "high"})
        return {"discrepancies": discrepancies}
    # TODO: match invoice lines to PO lines by item_code (or description fuzzy-match when code missing);
    #       compare qty (tol 0%), unit_price (tol 5%), currency; check vendor via erp_client.get_vendor(po['vendor_id']);
    #       emit {field_name, invoice_value, erp_value, deviation_pct, severity} per mismatch.
    return {"discrepancies": discrepancies}
