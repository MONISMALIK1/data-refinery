"""CSV profiling and schema-drift detection.

Profiling is the pipeline's smoke detector: cheap statistics computed on
every batch (columns, row counts, null rates) compared against the
baseline contract. Drift is detected here; repairing it is the fixer's
job.
"""
from __future__ import annotations

import csv
from pathlib import Path


def load_csv(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [dict(row) for row in csv.DictReader(f)]


def profile_rows(rows: list[dict]) -> dict:
    columns = list(rows[0].keys()) if rows else []
    null_rates = {}
    for col in columns:
        empty = sum(1 for r in rows if not str(r.get(col) or "").strip())
        null_rates[col] = round(empty / len(rows), 3) if rows else 0.0
    return {
        "row_count": len(rows),
        "columns": columns,
        "null_rates": null_rates,
    }


def detect_drift(columns: list[str], baseline: dict) -> dict:
    """Compare observed columns to the baseline contract."""
    expected = set(baseline["columns"])
    observed = set(columns)
    return {
        "has_drift": observed != expected,
        "missing_columns": sorted(expected - observed),
        "unexpected_columns": sorted(observed - expected),
    }
