-- audit schema: written by agent, read by streamlit-ui.
-- (langgraph schema is created by the LangGraph PostgresSaver .setup() call.)
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS langgraph;

CREATE TABLE audit.invoice_audit (
    invoice_id             UUID PRIMARY KEY,
    file_path              VARCHAR(512),
    file_checksum          VARCHAR(64) UNIQUE,          -- detects reprocessing
    extraction_method      VARCHAR(32),                 -- pdfplumber | docx | tesseract
    raw_extracted_text     TEXT,                        -- full text, pre-translation
    translated_text        TEXT,
    source_language        VARCHAR(8),
    translation_confidence NUMERIC(4,3),
    invoice_number         VARCHAR(64),
    vendor_name            VARCHAR(255),
    vendor_id              VARCHAR(16),
    po_number              VARCHAR(64),
    invoice_date           DATE,
    currency               CHAR(3),
    total_amount           NUMERIC(14,2),
    tax_amount             NUMERIC(14,2),
    validation_status      VARCHAR(32),                 -- passed | failed | partial
    recommendation         VARCHAR(32),                 -- approve | review | reject
    processing_status      VARCHAR(32) DEFAULT 'detected', -- detected | processed | error
    error_message          TEXT,                        -- failed files are recorded too
    extracted_raw          JSONB,                       -- variable leftovers
    report_json            JSONB,
    thread_id              VARCHAR(128),
    email_meta             JSONB,
    processed_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit.invoice_line_items (
    id          BIGSERIAL PRIMARY KEY,
    invoice_id  UUID REFERENCES audit.invoice_audit(invoice_id) ON DELETE CASCADE,
    line_number INTEGER,
    item_code   VARCHAR(64),
    description TEXT,
    quantity    NUMERIC(12,3),
    unit_price  NUMERIC(14,4),
    line_total  NUMERIC(14,2)
);

CREATE TABLE audit.discrepancies (
    id            BIGSERIAL PRIMARY KEY,
    invoice_id    UUID REFERENCES audit.invoice_audit(invoice_id) ON DELETE CASCADE,
    field_name    VARCHAR(64),
    invoice_value TEXT,
    erp_value     TEXT,
    deviation_pct NUMERIC(8,4),
    severity      VARCHAR(16),
    detected_at   TIMESTAMPTZ DEFAULT now()
);

-- Corrections are INSERT-only; the original extraction is never overwritten.
CREATE TABLE audit.human_feedback (
    id              BIGSERIAL PRIMARY KEY,
    invoice_id      UUID REFERENCES audit.invoice_audit(invoice_id),
    field_name      VARCHAR(64),
    original_value  TEXT,
    corrected_value TEXT,
    corrected_by    VARCHAR(128),
    corrected_at    TIMESTAMPTZ DEFAULT now(),
    revalidated     BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_audit_vendor ON audit.invoice_audit(vendor_name);
CREATE INDEX idx_audit_reco   ON audit.invoice_audit(recommendation, processed_at);
CREATE INDEX idx_disc_invoice ON audit.discrepancies(invoice_id);
