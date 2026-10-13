"""Indexing Agent: chunk stored text (from PostgreSQL) -> embed -> Qdrant. Qdrant is derived & rebuildable."""
COLLECTION = "invoices"


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks

# TODO: ensure_collection(); index_invoice(state) with payload {invoice_id, chunk_text, source_type('invoice'|'report'), vendor, language};
#       rebuild_from_postgres() reading audit.invoice_audit.raw_extracted_text / report_json (no OCR repeat).
