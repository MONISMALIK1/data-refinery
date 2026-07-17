"""End-to-end tests of the compiled graph with injected fake extractors.

No API key, no network: PDFs are blank test fixtures and the extractor
is a fake, so these tests exercise routing, fixing, PII scanning, the
quality gate, and decisions.
"""
from pathlib import Path

from refinery import build_graph

CLEAN_CSV = """txn_id,date,amount,currency,merchant,category
T-1001,2026-06-02,240.00,AED,Carrefour,grocery
T-1002,2026-06-05,89.50,AED,Careem,transport
"""

DRIFTED_CSV = """transaction_id,transaction_date,amount_aed,merchant_name,category
T-2001,03/07/2026,"1,150.00",Noon.com,electronics
T-2002,05/07/2026,89.50,Careem,transport
T-2002,05/07/2026,89.50,Careem,transport
"""

EMAILS = """From: ahmed.k@gulfsupplies.ae
Subject: Payment reminder
Date: 2026-07-10
---
Call me on +971 50 123 4567 about invoice INV-2026-001.
"""


class FakeExtractor:
    def __init__(self, records, confidence):
        self.records = records
        self.confidence = confidence
        self.calls = 0

    def __call__(self, state):
        self.calls += 1
        return {"records": self.records, "confidence": self.confidence, "method": "fake"}


FULL_INVOICE_RECORD = {
    "invoice_number": "INV-2026-001",
    "vendor": "Gulf Office Supplies LLC",
    "invoice_date": "2026-07-01",
    "due_date": "2026-08-01",
    "total_amount": 4520.0,
    "currency": "AED",
}


def write_blank_pdf(path: Path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def test_clean_csv_loads_without_fixes(tmp_path):
    path = tmp_path / "clean.csv"
    path.write_text(CLEAN_CSV)
    result = build_graph(extractor=FakeExtractor([], 0.0)).invoke({"file_path": str(path)})
    assert result["decision"]["action"] == "LOAD"
    assert result["fixes_applied"] == []
    assert result["record_kind"] == "transactions"
    assert len(result["records"]) == 2


def test_drifted_csv_is_repaired_and_loads(tmp_path):
    path = tmp_path / "drifted.csv"
    path.write_text(DRIFTED_CSV)
    result = build_graph(extractor=FakeExtractor([], 0.0)).invoke({"file_path": str(path)})
    assert result["decision"]["action"] == "LOAD"
    assert len(result["records"]) == 2  # duplicate dropped
    first = result["records"][0]
    assert first["txn_id"] == "T-2001"
    assert first["date"] == "2026-07-03"
    assert first["amount"] == 1150.0
    assert first["currency"] == "AED"
    assert any("renamed column" in fix for fix in result["fixes_applied"])


def test_pdf_with_confident_extractor_loads(tmp_path):
    path = tmp_path / "invoice.pdf"
    write_blank_pdf(path)
    extractor = FakeExtractor([FULL_INVOICE_RECORD], 0.95)
    result = build_graph(extractor=extractor).invoke({"file_path": str(path)})
    assert extractor.calls == 1
    assert result["record_kind"] == "invoices"
    assert result["decision"]["action"] == "LOAD"


def test_pdf_with_low_confidence_goes_to_review(tmp_path):
    path = tmp_path / "invoice.pdf"
    write_blank_pdf(path)
    result = build_graph(extractor=FakeExtractor([FULL_INVOICE_RECORD], 0.4)).invoke(
        {"file_path": str(path)}
    )
    assert result["decision"]["action"] == "REVIEW"


def test_email_with_pii_is_redacted_and_quarantined(tmp_path):
    path = tmp_path / "emails.txt"
    path.write_text(EMAILS)
    result = build_graph(extractor=FakeExtractor([], 0.0)).invoke({"file_path": str(path)})
    decision = result["decision"]
    assert result["record_kind"] == "documents"
    assert decision["action"] == "LOAD"
    assert decision["quarantine"] is True
    body = result["records"][0]["body"]
    assert "+971 50 123 4567" not in body
    assert "[REDACTED-PHONE]" in body
    assert "INV-2026-001" in body  # reference codes survive redaction
    types = {f["type"] for f in result["pii_findings"]}
    assert {"phone", "email"} <= types


def test_unknown_file_goes_to_review(tmp_path):
    path = tmp_path / "notes.docx"
    path.write_bytes(b"binary-ish content")
    result = build_graph(extractor=FakeExtractor([], 0.0)).invoke({"file_path": str(path)})
    assert result["decision"]["action"] == "REVIEW"
    assert "unclassified" in result["decision"]["reasons"][0]


def test_audit_trail_is_ordered(tmp_path):
    path = tmp_path / "clean.csv"
    path.write_text(CLEAN_CSV)
    result = build_graph(extractor=FakeExtractor([], 0.0)).invoke({"file_path": str(path)})
    stages = [line.split(":")[0] for line in result["audit_trail"]]
    assert stages == ["ingest", "classify", "profile", "fix", "pii_scan", "quality_gate", "decide"]
