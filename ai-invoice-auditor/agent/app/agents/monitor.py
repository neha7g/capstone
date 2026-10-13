"""Invoice Monitor Agent (no LLM).

Polls the mounted incoming folder, and for every new file:
  detect -> wait until fully written -> checksum -> skip if already in audit trail
  -> record in audit.invoice_audit -> route by type -> hand to the pipeline handler.
Every detected file is recorded; files that fail processing are marked 'error' (never silently dropped).
"""
import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Callable

from .. import db
from ..config import INCOMING_DIR, POLL_INTERVAL

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".docx", ".png"}
ROUTES = {".pdf": "pdf", ".docx": "docx", ".png": "image"}   # extraction path per file type
STABLE_SECONDS = 2        # file untouched this long => fully written
META_GRACE_SECONDS = 5    # wait this long for the matching .meta.json before processing without it

_checksum_cache: dict[tuple[str, float, int], str] = {}      # (path, mtime, size) -> sha256, avoids re-hashing every poll
_skipped: set[str] = set()                                   # checksums already logged as duplicates


def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def meta_path(invoice: Path) -> Path:
    return invoice.parent / f"{invoice.stem}.meta.json"


def load_email_meta(invoice: Path) -> dict:
    mp = meta_path(invoice)
    if not mp.exists():
        return {}
    try:
        return json.loads(mp.read_text())
    except json.JSONDecodeError:
        log.warning("unreadable email metadata %s", mp.name)
        return {"_meta_error": "invalid json"}


def route(path: Path) -> str:
    return ROUTES[path.suffix.lower()]


def _ready(p: Path, now: float) -> bool:
    """File fully written, and its email metadata has arrived (or the grace period is over)."""
    age = now - p.stat().st_mtime
    if age < STABLE_SECONDS:
        return False
    return meta_path(p).exists() or age >= META_GRACE_SECONDS


def _checksum(p: Path) -> str:
    st = p.stat()
    key = (str(p), st.st_mtime, st.st_size)
    if key not in _checksum_cache:
        _checksum_cache[key] = sha256_file(p)
    return _checksum_cache[key]


def scan_incoming() -> list[dict]:
    """Return new, not-yet-audited invoices (already recorded as 'detected')."""
    new: list[dict] = []
    if not INCOMING_DIR.exists():
        log.error("incoming dir %s missing", INCOMING_DIR)
        return new
    now = time.time()
    for p in sorted(INCOMING_DIR.iterdir()):
        if not p.is_file() or p.name.endswith(".meta.json") or p.suffix.lower() not in SUPPORTED:
            continue
        try:
            if not _ready(p, now):
                continue
            checksum = _checksum(p)
            if db.checksum_exists(checksum):                  # same content under any filename => skip
                if checksum not in _skipped:
                    log.info("skip %s: checksum already in audit trail", p.name)
                    _skipped.add(checksum)
                continue
            invoice_id = str(uuid.uuid4())
            meta = load_email_meta(p)
            if not db.record_detected(invoice_id, str(p), checksum, meta):
                continue                                      # lost a race with another poll
            log.info("detected %s -> %s (%s)", p.name, route(p), invoice_id)
            new.append({"invoice_id": invoice_id, "file_path": str(p), "checksum": checksum,
                        "email_meta": meta, "route": route(p)})
        except Exception as exc:                              # one bad file must not stop the scan
            log.exception("failed to inspect %s", p.name)
            _record_failure_for_path(p, exc)
    return new


def _record_failure_for_path(p: Path, exc: Exception) -> None:
    """File could not even be hashed/recorded normally: still leave a trace in the audit trail."""
    try:
        checksum = f"unreadable:{p.name}:{int(p.stat().st_mtime)}"[:64]
        iid = str(uuid.uuid4())
        if db.record_detected(iid, str(p), checksum, {}):
            db.mark_error(iid, f"monitor: {exc}")
    except Exception:
        log.exception("could not record failure for %s", p.name)


def process_one(item: dict, handler: Callable[[dict], None]) -> None:
    """Run the pipeline for one invoice; any failure is persisted on the audit row."""
    try:
        handler(item)
    except Exception as exc:
        log.exception("processing failed for %s", item["file_path"])
        db.mark_error(item["invoice_id"], f"{type(exc).__name__}: {exc}")


def handle_new_invoice(item: dict) -> None:
    """Default handler: extraction stage (raw text + parsed fields -> PostgreSQL).
    Replace/extend with graph.invoke(...) once the full LangGraph workflow is wired."""
    from .extractor import extract_invoice
    out = extract_invoice(item["file_path"])
    db.save_extraction(item["invoice_id"], out["extraction_method"], out["raw_text"],
                       out["header"], out["line_items"])
    log.info("extracted %s via %s: invoice_no=%s lines=%d", Path(item["file_path"]).name,
             out["extraction_method"], out["header"]["invoice_no"], len(out["line_items"]))


async def run_monitor(handler: Callable[[dict], None] = handle_new_invoice,
                      stop: asyncio.Event | None = None) -> None:
    """Background polling loop (blocking work runs in a thread so the API stays responsive)."""
    log.info("monitor watching %s every %ss", INCOMING_DIR, POLL_INTERVAL)
    while stop is None or not stop.is_set():
        try:
            for item in await asyncio.to_thread(scan_incoming):
                await asyncio.to_thread(process_one, item, handler)
        except Exception:
            log.exception("monitor cycle failed")
        await asyncio.sleep(POLL_INTERVAL)