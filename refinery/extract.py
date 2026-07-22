"""Text and record extraction from unstructured sources.

Two extractor backends implement the same contract -- a callable taking
the graph state and returning ``{"records": [...], "confidence": float,
"method": str}``:

- :class:`ClaudeExtractor` uses structured output, so the model is
  physically unable to return anything but a valid ``InvoiceExtraction``.
- :class:`RegexInvoiceExtractor` is the deterministic fallback (and the
  reason the demo and CI run with no API key): label-based parsing with
  confidence proportional to how many required fields were found.

The graph takes the extractor by injection, which is how tests swap in
fakes and how a different model could be dropped in without touching
pipeline code.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .fixers import coerce_date, coerce_number
from .models import EmailRecord, InvoiceExtraction, InvoiceRecord

DEFAULT_MODEL = "claude-sonnet-5"
OPENROUTER_DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

EXTRACTION_PROMPT = """You are a document data-entry specialist. Extract the
invoice fields from the document text below. If a field is absent, leave it
null and lower your confidence accordingly. Dates must be ISO YYYY-MM-DD.

Document text:
{text}"""


def extract_pdf_text(path: str | Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_email_export(text: str) -> list[dict]:
    """Parse a plain-text mailbox export: messages separated by ==== lines,
    headers separated from the body by a --- line."""
    emails: list[dict] = []
    for block in re.split(r"^={3,}\s*$", text, flags=re.MULTILINE):
        block = block.strip()
        if not block:
            continue
        headers, _, body = block.partition("\n---\n")
        fields = {"subject": "", "sender": "", "date": ""}
        for line in headers.splitlines():
            name, _, value = line.partition(":")
            key = {"from": "sender", "subject": "subject", "date": "date"}.get(
                name.strip().lower()
            )
            if key:
                fields[key] = value.strip()
        record = EmailRecord(body=body.strip() or headers, **fields)
        emails.append(record.model_dump())
    return emails


class RegexInvoiceExtractor:
    """Deterministic label-based invoice parsing."""

    FIELDS = {
        "invoice_number": re.compile(r"Invoice Number:\s*(\S+)"),
        "vendor": re.compile(r"Vendor:\s*(.+)"),
        "invoice_date": re.compile(r"Invoice Date:\s*([\d/\-]+)"),
        "due_date": re.compile(r"Due Date:\s*([\d/\-]+)"),
        "total": re.compile(r"Total:\s*([A-Z]{3})\s*([\d,\.]+)"),
    }

    def __call__(self, state: dict) -> dict:
        text = state["raw_text"]
        found = 0
        values: dict = {}

        for field in ("invoice_number", "vendor", "invoice_date", "due_date"):
            match = self.FIELDS[field].search(text)
            if match:
                value = match.group(1).strip()
                if field.endswith("date"):
                    value = coerce_date(value) or value
                values[field] = value
                if field != "due_date":  # due date is optional, not scored
                    found += 1

        total_match = self.FIELDS["total"].search(text)
        if total_match:
            values["currency"] = total_match.group(1)
            values["total_amount"] = coerce_number(total_match.group(2))
            found += 2  # currency + amount
        else:
            values["currency"] = "AED"

        if "invoice_number" not in values:
            return {"records": [], "confidence": 0.0, "method": "regex"}

        record = InvoiceRecord(
            invoice_number=values["invoice_number"],
            vendor=values.get("vendor", "UNKNOWN"),
            invoice_date=values.get("invoice_date"),
            due_date=values.get("due_date"),
            total_amount=values.get("total_amount"),
            currency=values.get("currency", "AED"),
        )
        confidence = round(found / 5.0, 3)  # number, vendor, date, currency, amount
        return {"records": [record.model_dump()], "confidence": confidence, "method": "regex"}


class ClaudeExtractor:
    """LLM extraction with structured output; falls back to regex when no
    API key is configured so the pipeline never depends on the model
    being available."""

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("REFINERY_MODEL", DEFAULT_MODEL)
        self.fallback = RegexInvoiceExtractor()

    def _get_llm(self):
        if os.environ.get("ANTHROPIC_API_KEY"):
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=self.model, temperature=0.0, max_tokens=1024), "claude"
        if os.environ.get("OPENROUTER_API_KEY"):
            from langchain_openai import ChatOpenAI
            model = os.environ.get("REFINERY_MODEL", OPENROUTER_DEFAULT_MODEL)
            return ChatOpenAI(
                model=model,
                openai_api_key=os.environ["OPENROUTER_API_KEY"],
                openai_api_base=OPENROUTER_BASE_URL,
                temperature=0.0,
                max_tokens=1024,
            ), "openrouter"
        return None, None

    def __call__(self, state: dict) -> dict:
        llm, method = self._get_llm()
        if llm is None:
            return self.fallback(state)
        structured = llm.with_structured_output(InvoiceExtraction)
        result = structured.invoke(EXTRACTION_PROMPT.format(text=state["raw_text"][:8000]))
        return {
            "records": [result.invoice.model_dump()],
            "confidence": result.confidence,
            "method": method,
        }
