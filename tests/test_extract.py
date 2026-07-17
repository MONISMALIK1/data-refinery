from refinery.extract import RegexInvoiceExtractor, parse_email_export

FULL_INVOICE = """INVOICE
Invoice Number: INV-2026-001
Vendor: Gulf Office Supplies LLC
Invoice Date: 2026-07-01
Due Date: 2026-08-01
Items: Office chairs x 8
Total: AED 4,520.00"""

PARTIAL_INVOICE = """INVOICE
Invoice Number: INV-2026-003
Vendor: Creek Marketing Agency
Invoice Date: 2026-07-08
Note: Amount to be confirmed after scope review."""


def test_regex_extractor_full_invoice():
    result = RegexInvoiceExtractor()({"raw_text": FULL_INVOICE})
    assert result["confidence"] == 1.0
    record = result["records"][0]
    assert record["invoice_number"] == "INV-2026-001"
    assert record["vendor"] == "Gulf Office Supplies LLC"
    assert record["total_amount"] == 4520.0
    assert record["currency"] == "AED"
    assert record["due_date"] == "2026-08-01"


def test_regex_extractor_partial_invoice_lowers_confidence():
    result = RegexInvoiceExtractor()({"raw_text": PARTIAL_INVOICE})
    assert result["confidence"] == 0.6
    assert result["records"][0]["total_amount"] is None


def test_regex_extractor_gives_up_without_invoice_number():
    result = RegexInvoiceExtractor()({"raw_text": "just some text"})
    assert result == {"records": [], "confidence": 0.0, "method": "regex"}


def test_parse_email_export():
    text = (
        "From: a@b.ae\nSubject: Hello\nDate: 2026-07-10\n---\nBody one\n"
        "=====\n"
        "From: c@d.ae\nSubject: Second\nDate: 2026-07-12\n---\nBody two"
    )
    emails = parse_email_export(text)
    assert len(emails) == 2
    assert emails[0]["sender"] == "a@b.ae"
    assert emails[0]["subject"] == "Hello"
    assert emails[0]["body"] == "Body one"
    assert emails[1]["body"] == "Body two"
