"""data-refinery: LangGraph agent that turns messy mixed-format files
into governed, PII-safe, AI-ready datasets in DuckDB."""

from .extract import ClaudeExtractor, RegexInvoiceExtractor
from .graph import RefineryState, build_graph
from .models import EmailRecord, InvoiceRecord, TransactionRecord

__all__ = [
    "build_graph",
    "RefineryState",
    "ClaudeExtractor",
    "RegexInvoiceExtractor",
    "TransactionRecord",
    "InvoiceRecord",
    "EmailRecord",
]

__version__ = "1.0.0"
