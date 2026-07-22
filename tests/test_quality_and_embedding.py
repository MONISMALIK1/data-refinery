from refinery.embedding import cosine, embed
from refinery.quality import completeness, gate


def test_embedding_is_deterministic_and_normalised():
    a = embed("invoice from gulf office supplies")
    b = embed("invoice from gulf office supplies")
    assert a == b
    assert abs(cosine(a, a) - 1.0) < 1e-6


def test_related_text_scores_higher_than_unrelated():
    invoice = embed("Invoice INV-2026-001 from Gulf Office Supplies total 4520 AED")
    query = embed("how much do we owe gulf office supplies")
    unrelated = embed("driver gate pass emirates id registration")
    assert cosine(query, invoice) > cosine(query, unrelated)


def test_completeness():
    records = [
        {"invoice_number": "INV-1", "vendor": "A", "total_amount": 10.0},
        {"invoice_number": "INV-2", "vendor": "B", "total_amount": None},
    ]
    assert completeness(records, "invoices") == round((1.0 + 2 / 3) / 2, 3)
    assert completeness([], "invoices") == 0.0


def test_gate_thresholds():
    full = [{"invoice_number": "INV-1", "vendor": "A", "total_amount": 10.0}]
    score, verdict = gate(full, "invoices", base_confidence=1.0)
    assert (score, verdict) == (1.0, "LOAD")

    score, verdict = gate(full, "invoices", base_confidence=0.6)
    assert verdict == "REVIEW"
