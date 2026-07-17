"""Quality gate: the last check before anything reaches the warehouse.

Score = extractor confidence x field completeness. Records only load
above LOAD_THRESHOLD; everything else goes to the human review queue.
The gate never repairs anything -- repairs happen upstream where they
can be logged as fixes -- it only measures and decides.
"""
from __future__ import annotations

from .config import LOAD_THRESHOLD

REQUIRED_FIELDS = {
    "transactions": ["txn_id", "date", "amount"],
    "invoices": ["invoice_number", "vendor", "total_amount"],
    "documents": ["body"],
}


def completeness(records: list[dict], kind: str) -> float:
    required = REQUIRED_FIELDS.get(kind, [])
    if not records or not required:
        return 0.0 if not records else 1.0
    total = 0.0
    for record in records:
        present = sum(
            1 for field in required if record.get(field) not in (None, "", [])
        )
        total += present / len(required)
    return round(total / len(records), 3)


def gate(records: list[dict], kind: str, base_confidence: float) -> tuple[float, str]:
    """Return (quality_score, decision)."""
    score = round(base_confidence * completeness(records, kind), 3)
    return score, ("LOAD" if score >= LOAD_THRESHOLD else "REVIEW")
