"""PII detection and redaction.

Runs BEFORE anything is stored or embedded: once personal data lands in
a warehouse table or a vector index it is effectively unremovable (an
embedding cannot be un-trained from the text that produced it). So the
scan sits in the mandatory path of the graph, and originals containing
PII are quarantined rather than loaded.

Deterministic regex detection, ordered most-specific first so an
Emirates ID is not half-matched as a phone number.
"""
from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("emirates_id", re.compile(r"784[-\s]?\d{4}[-\s]?\d{7}[-\s]?\d")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,28}\b")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # The (?<![\w-]) lookbehind stops half-matching reference codes like
    # INV-2026-001, whose numeric tail is phone-shaped.
    (
        "phone",
        re.compile(
            r"(?<![\w-])(?:\+\d{1,3}[\s-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s-]\d{3}[\s-]?\d{3,4}(?!\d)"
        ),
    ),
]


def _preview(match: str) -> str:
    """Keep only enough of the match to recognise it in a review queue."""
    return match[:4] + "***" if len(match) > 4 else "***"


def scan_and_redact(text: str) -> tuple[str, list[dict]]:
    """Return (redacted_text, findings). Findings never contain the full value."""
    findings: list[dict] = []
    redacted = text
    for pii_type, pattern in PATTERNS:
        for match in pattern.findall(redacted):
            findings.append({"type": pii_type, "preview": _preview(match)})
        redacted = pattern.sub(f"[REDACTED-{pii_type.upper()}]", redacted)
    return redacted, findings


def redact_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Redact every string field of every record."""
    findings: list[dict] = []
    cleaned: list[dict] = []
    for record in records:
        new_record = {}
        for key, value in record.items():
            if isinstance(value, str):
                redacted, found = scan_and_redact(value)
                new_record[key] = redacted
                findings.extend(found)
            else:
                new_record[key] = value
        cleaned.append(new_record)
    return cleaned, findings
