"""Mock ERP: the ONLY route to the `erp` schema. Read-only."""
import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _dsn() -> str:
    # Fail fast with a clear message if config is missing (reliability NFR).
    try:
        return (f"host={os.environ.get('POSTGRES_HOST', 'postgres')} "
                f"port={os.environ.get('POSTGRES_PORT', '5432')} "
                f"dbname={os.environ['POSTGRES_DB']} "
                f"user={os.environ['POSTGRES_USER']} "
                f"password={os.environ['POSTGRES_PASSWORD']}")
    except KeyError as e:
        raise RuntimeError(f"Missing required environment variable: {e}") from e


pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = ConnectionPool(_dsn(), min_size=1, max_size=5, kwargs={"row_factory": dict_row}, open=False)
    pool.open(wait=True, timeout=15)          # raises -> container exits clearly if DB unreachable
    yield
    pool.close()


app = FastAPI(title="Mock ERP", lifespan=lifespan)


def _one(sql, params):
    with pool.connection() as c:
        return c.execute(sql, params).fetchone()


def _all(sql, params):
    with pool.connection() as c:
        return c.execute(sql, params).fetchall()


@app.get("/health")
def health():
    _one("SELECT 1 AS ok", ())
    return {"status": "ok"}


@app.get("/vendor/{vendor_id}")
def vendor(vendor_id: str):
    row = _one("SELECT * FROM erp.vendors WHERE vendor_id=%s", (vendor_id,))
    if not row:
        raise HTTPException(404, f"Vendor {vendor_id} not found")
    return row


@app.get("/po/{po_number}")
def po(po_number: str):
    head = _one("SELECT * FROM erp.purchase_orders WHERE po_number=%s", (po_number,))
    if not head:
        raise HTTPException(404, f"PO {po_number} not found")
    lines = _all("SELECT item_code, description, qty, unit_price, currency "
                 "FROM erp.po_line_items WHERE po_number=%s ORDER BY id", (po_number,))
    return {**head, "line_items": lines}


@app.get("/sku/{sku_code}")
def sku(sku_code: str):
    row = _one("SELECT * FROM erp.sku_master WHERE item_code=%s", (sku_code,))
    if not row:
        raise HTTPException(404, f"SKU {sku_code} not found")
    return row


# Convenience for the agent's vendor-name -> vendor_id resolution (still HTTP, still the ERP boundary).
@app.get("/vendors")
def vendors():
    return _all("SELECT * FROM erp.vendors ORDER BY vendor_id", ())
