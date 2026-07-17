"""DuckDB warehouse: typed tables, vector chunks, and lineage.

Loading is deliberately OUTSIDE the graph: the graph is a pure
transform-and-decide pipeline (easy to test, safe to re-run), and this
module is the only place with side effects. Every processed file gets a
lineage row whether it loaded or not -- "we rejected it" is part of the
audit trail too.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .embedding import cosine, embed

DDL = [
    """CREATE TABLE IF NOT EXISTS transactions (
        txn_id VARCHAR, date VARCHAR, amount DOUBLE, currency VARCHAR,
        merchant VARCHAR, category VARCHAR, source_file VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS invoices (
        invoice_number VARCHAR, vendor VARCHAR, invoice_date VARCHAR,
        due_date VARCHAR, total_amount DOUBLE, currency VARCHAR, source_file VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS documents (
        subject VARCHAR, sender VARCHAR, date VARCHAR, body VARCHAR, source_file VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS chunks (
        source_file VARCHAR, kind VARCHAR, text VARCHAR, embedding DOUBLE[])""",
    """CREATE TABLE IF NOT EXISTS lineage (
        source_file VARCHAR, file_type VARCHAR, decision VARCHAR, record_kind VARCHAR,
        records_loaded INTEGER, quality_score DOUBLE, extraction_method VARCHAR,
        fixes VARCHAR, unfixed VARCHAR, pii_types VARCHAR, quarantined BOOLEAN,
        audit VARCHAR, processed_at TIMESTAMP DEFAULT current_timestamp)""",
]


def _chunk_text(result: dict) -> list[str]:
    """One retrievable text per loaded unit, phrased for search."""
    kind = result.get("record_kind")
    records = result.get("records", [])
    name = Path(result["file_path"]).name
    if kind == "invoices":
        return [
            f"Invoice {r.get('invoice_number')} from {r.get('vendor')}: "
            f"total {r.get('total_amount')} {r.get('currency')}, "
            f"invoice date {r.get('invoice_date')}, due date {r.get('due_date')}."
            for r in records
        ]
    if kind == "documents":
        return [
            f"Email from {r.get('sender')} on {r.get('date')}, "
            f"subject '{r.get('subject')}': {r.get('body')}"
            for r in records
        ]
    if kind == "transactions" and records:
        dates = sorted(str(r.get("date")) for r in records)
        total = sum(float(r.get("amount") or 0) for r in records)
        categories = ", ".join(sorted({str(r.get("category")) for r in records}))
        merchants = ", ".join(sorted({str(r.get("merchant")) for r in records}))
        return [
            f"Transactions file {name}: {len(records)} rows from {dates[0]} to "
            f"{dates[-1]}, total {total:.2f}, merchants {merchants}, categories {categories}."
        ]
    return []


def load_results(results: list[dict], db_path: str | Path) -> dict:
    """Persist graph outputs. Returns counts per destination."""
    counts = {"transactions": 0, "invoices": 0, "documents": 0, "chunks": 0, "review": 0}
    con = duckdb.connect(str(db_path))
    for statement in DDL:
        con.execute(statement)

    for result in results:
        decision = result.get("decision", {})
        records = result.get("records", [])
        kind = result.get("record_kind")
        name = Path(result["file_path"]).name

        if decision.get("action") == "LOAD" and kind in ("transactions", "invoices", "documents"):
            for r in records:
                if kind == "transactions":
                    con.execute(
                        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [r.get("txn_id"), r.get("date"), r.get("amount"), r.get("currency"),
                         r.get("merchant"), r.get("category"), name],
                    )
                elif kind == "invoices":
                    con.execute(
                        "INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [r.get("invoice_number"), r.get("vendor"), r.get("invoice_date"),
                         r.get("due_date"), r.get("total_amount"), r.get("currency"), name],
                    )
                else:
                    con.execute(
                        "INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
                        [r.get("subject"), r.get("sender"), r.get("date"), r.get("body"), name],
                    )
                counts[kind] += 1
            for text in _chunk_text(result):
                con.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?)", [name, kind, text, embed(text)]
                )
                counts["chunks"] += 1
        else:
            counts["review"] += 1

        pii_types = ",".join(sorted({f["type"] for f in result.get("pii_findings", [])}))
        con.execute(
            """INSERT INTO lineage (source_file, file_type, decision, record_kind,
               records_loaded, quality_score, extraction_method, fixes, unfixed,
               pii_types, quarantined, audit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                name,
                result.get("file_type"),
                decision.get("action", "REVIEW"),
                kind,
                len(records) if decision.get("action") == "LOAD" else 0,
                decision.get("quality_score", 0.0),
                result.get("extraction_method"),
                json.dumps(result.get("fixes_applied", [])),
                json.dumps(result.get("unfixed_issues", [])),
                pii_types,
                bool(result.get("pii_findings")),
                json.dumps(result.get("audit_trail", [])),
            ],
        )
    con.close()
    return counts


def search_chunks(db_path: str | Path, query: str, k: int = 3) -> list[dict]:
    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute("SELECT source_file, kind, text, embedding FROM chunks").fetchall()
    con.close()
    query_vector = embed(query)
    scored = [
        {"source_file": source, "kind": kind, "text": text,
         "score": round(cosine(query_vector, list(vector)), 4)}
        for source, kind, text, vector in rows
    ]
    scored.sort(key=lambda h: h["score"], reverse=True)
    return scored[:k]


def lineage_report(db_path: str | Path) -> list[tuple]:
    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute(
        """SELECT source_file, file_type, decision, records_loaded, quality_score,
                  pii_types, quarantined FROM lineage ORDER BY processed_at, source_file"""
    ).fetchall()
    con.close()
    return rows
