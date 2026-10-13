# AI Invoice Auditor

Containerized multilingual invoice validation: monitor -> extract -> translate -> validate (via mock-erp) -> report -> RAG, with a Streamlit HITL dashboard.

## Quick start (clean checkout)
```bash
cp .env.example .env        # fill in AWS creds + POSTGRES_PASSWORD
docker compose up --build -d
docker compose ps           # all six services healthy
python scripts/simulate_email.py   # drops sample invoices into data/incoming
```
UI: http://localhost:8501 · Agent: http://localhost:8000/health · ERP: http://localhost:8001/po/PO-1001

## Services
| Service | Host:Container | Role |
|---|---|---|
| agent | 8000:8000 | LangGraph pipeline + RAG, only writer of app data |
| mock-erp | 8001:8000 | FastAPI over `erp` schema, only route to ERP data |
| streamlit-ui | 8501:8501 | Auditor dashboard |
| postgres | 5432:5432 | schemas: langgraph, erp, audit (named volume `pgdata`) |
| qdrant | 6333:6333 | derived vector index (named volume `qdrantdata`) |
| redis | 6379:6379 | disposable LLM/translation cache (no volume) |

## Persistence checks
- `docker compose down` then `up -d` -> audit trail + RAG index intact (volumes kept).
- `docker compose down -v` then `up -d` -> both empty (`-v` removes named volumes). ERP re-seeds from `db/init`.
- `docker history my-agent:1.0 --no-trunc` -> no secrets (credentials only via `env_file`).

## Layout
`agent/` · `mock_erp/` · `streamlit_ui/` · `db/init/` (ERP seed + audit schema) · `configs/` (rules, personas, prompts) · `data/` · `outputs/`

## Status
Skeleton: infrastructure complete; agent logic marked `TODO` in code.
