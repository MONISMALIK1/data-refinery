from refinery.classify import classify_file
from refinery.config import TRANSACTIONS_BASELINE
from refinery.profiling import detect_drift, profile_rows


def test_classify_by_extension_and_content(tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n")
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    email = tmp_path / "mail.txt"
    email.write_text("From: a@b.ae\nSubject: hi\n---\nbody")
    plain = tmp_path / "notes.txt"
    plain.write_text("just some notes")

    assert classify_file(csv) == "csv"
    assert classify_file(pdf) == "pdf"
    assert classify_file(email) == "email"
    assert classify_file(plain) == "unknown"
    assert classify_file(tmp_path / "img.png") == "unknown"


def test_profile_rows_null_rates():
    rows = [{"a": "1", "b": ""}, {"a": "2", "b": "x"}]
    profile = profile_rows(rows)
    assert profile["row_count"] == 2
    assert profile["null_rates"] == {"a": 0.0, "b": 0.5}


def test_detect_drift():
    clean = detect_drift(TRANSACTIONS_BASELINE["columns"], TRANSACTIONS_BASELINE)
    assert clean["has_drift"] is False

    drifted = detect_drift(["transaction_id", "amount"], TRANSACTIONS_BASELINE)
    assert drifted["has_drift"] is True
    assert "txn_id" in drifted["missing_columns"]
    assert "transaction_id" in drifted["unexpected_columns"]
