"""Extraction schemas.

Every record that enters the warehouse is validated against one of these
Pydantic models first. LLM extractors are forced through the same
schemas via structured output, so a hallucinated field name or a string
where a number belongs fails loudly at the boundary instead of
poisoning the warehouse.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TransactionRecord(BaseModel):
    txn_id: str
    date: str  # ISO YYYY-MM-DD after fixing
    amount: float
    currency: str = "AED"
    merchant: str
    category: str = "general"


class InvoiceRecord(BaseModel):
    invoice_number: str
    vendor: str
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str = "AED"


class EmailRecord(BaseModel):
    subject: str = ""
    sender: str = ""
    date: str = ""
    body: str


class InvoiceExtraction(BaseModel):
    """What the LLM extractor must return for an invoice document."""

    invoice: InvoiceRecord
    confidence: float = Field(
        description="How confident the extractor is (0.0–1.0) that every field is correct."
    )
    notes: str = Field(default="", description="Anything ambiguous or missing in the source.")
