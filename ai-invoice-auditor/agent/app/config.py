"""Central configuration. All secrets/hosts come from the environment - nothing hard-coded."""
import logging
import os
import sys
from pathlib import Path

import yaml


def env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


POSTGRES_DSN = (f"host={env('POSTGRES_HOST', 'postgres')} port={env('POSTGRES_PORT', '5432')} "
                f"dbname={env('POSTGRES_DB')} user={env('POSTGRES_USER')} password={env('POSTGRES_PASSWORD')}")
QDRANT_URL = env("QDRANT_URL", "http://qdrant:6333")
REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")
ERP_BASE_URL = env("ERP_BASE_URL", "http://mock-erp:8000")
INCOMING_DIR = Path(env("INCOMING_DIR", "/data/incoming"))
REPORTS_DIR = Path(env("REPORTS_DIR", "/outputs/reports"))
RULES_PATH = Path(env("RULES_PATH", "/app/configs/rules.yaml"))
POLL_INTERVAL = int(env("POLL_INTERVAL_SECONDS", "10"))

REASONING_MODEL = env("REASONING_MODEL", "bedrock/amazon.nova-lite-v1:0")
RAG_MODEL = env("RAG_MODEL", "bedrock/cohere.command-r-plus-v1:0")
TRANSLATION_MODEL = env("TRANSLATION_MODEL", "bedrock/cohere.command-r-plus-v1:0")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "bedrock/amazon.titan-embed-text-v2:0")


def load_rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text())


def setup_logging() -> None:
    # stdout only - never a file inside the container.
    logging.basicConfig(stream=sys.stdout, level=env("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
