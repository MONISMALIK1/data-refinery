"""File classification: decide which processing path a file takes.

Extension first, content sniff second. Deliberately boring -- the router
must never be a model call, because a misrouted file is the hardest
failure to debug downstream.
"""
from __future__ import annotations

from pathlib import Path


def classify_file(path: str | Path) -> str:
    """Return one of: csv, pdf, email, unknown."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".eml", ".txt"}:
        try:
            head = p.read_text(errors="ignore")[:2000]
        except OSError:
            return "unknown"
        if "From:" in head and "Subject:" in head:
            return "email"
        return "unknown"
    return "unknown"
