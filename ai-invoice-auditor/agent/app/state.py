"""Shared LangGraph state for one invoice."""
from typing import Any, TypedDict


class InvoiceState(TypedDict, total=False):
    invoice_id: str
    file_path: str
    checksum: str
    email_meta: dict
    extraction_method: str
    raw_text: str
    translated_text: str
    source_language: str
    translation_confidence: float
    header: dict                  # invoice_no, invoice_date, vendor_name, po_number, currency, total_amount, tax_amount
    line_items: list[dict]
    missing_fields: list[str]
    discrepancies: list[dict]     # {field_name, invoice_value, erp_value, deviation_pct, severity}
    validation_status: str        # passed | failed | partial
    recommendation: str           # approve | review | reject
    report: dict[str, Any]
    error: str
