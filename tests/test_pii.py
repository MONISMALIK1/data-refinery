from refinery.pii import redact_records, scan_and_redact


def types_of(findings):
    return {f["type"] for f in findings}


def test_detects_and_redacts_phone_numbers():
    redacted, findings = scan_and_redact("Call me on +971 50 123 4567 today")
    assert "phone" in types_of(findings)
    assert "+971 50 123 4567" not in redacted
    assert "[REDACTED-PHONE]" in redacted


def test_detects_email_iban_and_emirates_id():
    text = (
        "Contact ahmed.k@gulfsupplies.ae, IBAN AE070331234567890123456, "
        "Emirates ID 784-1990-1234567-1"
    )
    redacted, findings = scan_and_redact(text)
    assert {"email", "iban", "emirates_id"} <= types_of(findings)
    assert "ahmed.k@gulfsupplies.ae" not in redacted
    assert "784-1990-1234567-1" not in redacted


def test_findings_never_contain_full_values():
    _, findings = scan_and_redact("Reach me on 055-987-6543")
    assert all(len(f["preview"]) <= 7 for f in findings)
    assert all("***" in f["preview"] for f in findings)


def test_invoice_numbers_and_dates_are_not_false_positives():
    text = "Invoice INV-2026-001 dated 2026-08-01 for AED 4,520.00"
    redacted, findings = scan_and_redact(text)
    assert findings == []
    assert redacted == text


def test_redact_records_cleans_string_fields_only():
    records = [{"body": "call 055-987-6543", "amount": 42.5}]
    cleaned, findings = redact_records(records)
    assert "[REDACTED-PHONE]" in cleaned[0]["body"]
    assert cleaned[0]["amount"] == 42.5
    assert types_of(findings) == {"phone"}
