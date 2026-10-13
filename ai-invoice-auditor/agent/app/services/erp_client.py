"""HTTP client for mock-erp. The ONLY way the agent may read ERP data (no SQL on the erp schema)."""
import httpx

from ..config import ERP_BASE_URL

_client = httpx.Client(base_url=ERP_BASE_URL, timeout=10)


def _get(path: str) -> dict | None:
    r = _client.get(path)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def get_po(po_number: str): return _get(f"/po/{po_number}")
def get_vendor(vendor_id: str): return _get(f"/vendor/{vendor_id}")
def get_sku(sku_code: str): return _get(f"/sku/{sku_code}")
def list_vendors(): return _get("/vendors") or []
