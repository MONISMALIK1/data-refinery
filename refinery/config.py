"""Baseline contracts for structured sources.

A baseline is the pipeline's memory of what a feed is supposed to look
like. Drift detection compares each incoming file against it; the fixer
uses the synonym map and defaults to repair known, mechanical drift
without any model involvement.
"""

TRANSACTIONS_BASELINE = {
    "record_kind": "transactions",
    "columns": ["txn_id", "date", "amount", "currency", "merchant", "category"],
    # Common upstream renames we know how to undo deterministically.
    "synonyms": {
        "transaction_id": "txn_id",
        "transactionid": "txn_id",
        "transaction_date": "date",
        "txn_date": "date",
        "amount_aed": "amount",
        "amount_usd": "amount",
        "merchant_name": "merchant",
        "merchant_category": "category",
    },
    # Filled when a column is missing entirely.
    "defaults": {"currency": "AED", "category": "general"},
    # A synonym match on these implies the currency default.
    "currency_implying_columns": {"amount_aed": "AED", "amount_usd": "USD"},
    "date_columns": ["date"],
    "numeric_columns": ["amount"],
    "required": ["txn_id", "date", "amount"],
}

# Quality-gate thresholds: score = extractor confidence x field completeness.
LOAD_THRESHOLD = 0.75

EMBEDDING_DIM = 256
