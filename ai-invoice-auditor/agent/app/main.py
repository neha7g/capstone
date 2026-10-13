"""Agent service entrypoint (container port 8000): health, revalidate, RAG query endpoints."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import db
from .config import setup_logging

setup_logging()
log = logging.getLogger("agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open_pool()       # raises if postgres is unreachable -> container fails clearly
    # TODO: ensure Qdrant collection exists (fail fast if qdrant unreachable); ping redis;
    #       init PostgresSaver (langgraph schema) + build_graph(); start monitor polling task.
    log.info("agent ready")
    yield


app = FastAPI(title="Invoice Auditor Agent", lifespan=lifespan)


@app.get("/health")
def health():
    with db.pool.connection() as c:
        c.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/revalidate/{invoice_id}")
def revalidate(invoice_id: str):
    # TODO: load latest human_feedback corrections (INSERT-only), re-run validation + report, mark revalidated=TRUE
    raise NotImplementedError


@app.post("/query")
def query(payload: dict):
    # TODO: SQL path for structured questions; else rag.graph.run(question, invoice_id=payload.get("invoice_id"))
    raise NotImplementedError
