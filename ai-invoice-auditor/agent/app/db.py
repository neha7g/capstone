"""PostgreSQL access (audit schema only; ERP data goes through services/erp_client.py)."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import POSTGRES_DSN

pool = ConnectionPool(POSTGRES_DSN, min_size=1, max_size=5, kwargs={"row_factory": dict_row}, open=False)


def open_pool() -> None:
    pool.open(wait=True, timeout=20)   # fail clearly if postgres unreachable


def checksum_exists(checksum: str) -> bool:
    with pool.connection() as c:
        return c.execute("SELECT 1 FROM audit.invoice_audit WHERE file_checksum=%s", (checksum,)).fetchone() is not None


def record_detected(invoice_id: str, file_path: str, checksum: str, email_meta: dict | None) -> None:
    """Every detected file is recorded, including ones that later fail."""
    from psycopg.types.json import Jsonb
    with pool.connection() as c:
        c.execute("""INSERT INTO audit.invoice_audit (invoice_id, file_path, file_checksum, email_meta, processing_status)
                     VALUES (%s,%s,%s,%s,'detected') ON CONFLICT (file_checksum) DO NOTHING""",
                  (invoice_id, file_path, checksum, Jsonb(email_meta or {})))

# TODO: save_extraction(), save_line_items(), save_discrepancies(), save_report(), save_feedback(), mark_error()
