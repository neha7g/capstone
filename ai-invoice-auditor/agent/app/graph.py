"""LangGraph workflow: extract -> translate -> data validation -> business validation -> report -> index."""
from langgraph.graph import END, StateGraph

from .agents.business_validation import business_validation_node
from .agents.data_validation import data_validation_node
from .agents.reporting import reporting_node
from .agents.translation import translation_node
from .state import InvoiceState


def extract_node(state: InvoiceState) -> dict:
    from .agents.extractor import extract_text
    text, method = extract_text(state["file_path"])
    # TODO: persist raw text, parse header/line_items (see extractor TODO)
    return {"raw_text": text, "extraction_method": method}


def index_node(state: InvoiceState) -> dict:
    # TODO: call rag.indexing.index_invoice(state) -> chunks of invoice text + report text -> Qdrant
    return {}


def build_graph(checkpointer=None):
    g = StateGraph(InvoiceState)
    g.add_node("extract", extract_node)
    g.add_node("translate", translation_node)
    g.add_node("data_validation", data_validation_node)
    g.add_node("business_validation", business_validation_node)
    g.add_node("report", reporting_node)
    g.add_node("index", index_node)
    g.set_entry_point("extract")
    for a, b in [("extract", "translate"), ("translate", "data_validation"),
                 ("data_validation", "business_validation"), ("business_validation", "report"),
                 ("report", "index"), ("index", END)]:
        g.add_edge(a, b)
    return g.compile(checkpointer=checkpointer)   # PostgresSaver (schema: langgraph) passed from main.py
