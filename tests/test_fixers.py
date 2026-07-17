from refinery.config import TRANSACTIONS_BASELINE
from refinery.fixers import coerce_date, coerce_number, fix_rows


def test_coerce_date_formats():
    assert coerce_date("2026-07-16") == "2026-07-16"
    assert coerce_date("16/07/2026") == "2026-07-16"
    assert coerce_date("16-07-2026") == "2026-07-16"
    assert coerce_date("not a date") is None


def test_coerce_number():
    assert coerce_number("1,200.50") == 1200.50
    assert coerce_number("AED 950") == 950.0
    assert coerce_number(42) == 42.0
    assert coerce_number("n/a") is None


def test_fix_rows_repairs_known_drift():
    rows = [
        {
            "transaction_id": "T-1",
            "transaction_date": "03/07/2026",
            "amount_aed": "1,150.00",
            "merchant_name": "Noon.com",
            "category": "electronics",
        },
        {
            "transaction_id": "T-2",
            "transaction_date": "05/07/2026",
            "amount_aed": "89.50",
            "merchant_name": "Careem",
            "category": "transport",
        },
        {  # exact duplicate of T-2
            "transaction_id": "T-2",
            "transaction_date": "05/07/2026",
            "amount_aed": "89.50",
            "merchant_name": "Careem",
            "category": "transport",
        },
    ]
    fixed, fixes, unfixed = fix_rows(rows, TRANSACTIONS_BASELINE)

    assert unfixed == []
    assert len(fixed) == 2  # duplicate dropped
    first = fixed[0]
    assert first["txn_id"] == "T-1"
    assert first["date"] == "2026-07-03"
    assert first["amount"] == 1150.0
    assert first["currency"] == "AED"  # implied by amount_aed
    assert first["merchant"] == "Noon.com"
    joined = " | ".join(fixes)
    assert "renamed column" in joined
    assert "duplicate" in joined


def test_fix_rows_reports_unfixable():
    rows = [{"transaction_id": "T-1", "amount": "n/a"}]
    _, _, unfixed = fix_rows(rows, TRANSACTIONS_BASELINE)
    assert any("missing required column 'date'" in issue for issue in unfixed)
    assert any("unparseable number" in issue for issue in unfixed)
