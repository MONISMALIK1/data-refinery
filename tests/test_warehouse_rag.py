import duckdb

from refinery.rag import answer
from refinery.warehouse import load_results, search_chunks


def make_result(**overrides) -> dict:
    base = {
        "file_path": "demo/invoice_001.pdf",
        "file_type": "pdf",
        "record_kind": "invoices",
        "records": [
            {
                "invoice_number": "INV-2026-001",
                "vendor": "Gulf Office Supplies LLC",
                "invoice_date": "2026-07-01",
                "due_date": "2026-08-01",
                "total_amount": 4520.0,
                "currency": "AED",
            }
        ],
        "decision": {"action": "LOAD", "quality_score": 1.0, "quarantine": False, "reasons": []},
        "pii_findings": [],
        "fixes_applied": [],
        "unfixed_issues": [],
        "extraction_method": "fake",
        "audit_trail": ["test"],
    }
    base.update(overrides)
    return base


def test_load_results_populates_tables_and_lineage(tmp_path):
    db = tmp_path / "test.duckdb"
    review = make_result(
        file_path="demo/invoice_003.pdf",
        records=[],
        decision={"action": "REVIEW", "quality_score": 0.4, "quarantine": False, "reasons": []},
    )
    counts = load_results([make_result(), review], db)

    assert counts["invoices"] == 1
    assert counts["chunks"] == 1
    assert counts["review"] == 1

    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT count(*) FROM invoices").fetchone()[0] == 1
    lineage = con.execute("SELECT source_file, decision FROM lineage ORDER BY source_file").fetchall()
    con.close()
    assert lineage == [("invoice_001.pdf", "LOAD"), ("invoice_003.pdf", "REVIEW")]


def test_search_finds_the_relevant_chunk(tmp_path):
    db = tmp_path / "test.duckdb"
    email_result = make_result(
        file_path="demo/emails.txt",
        file_type="email",
        record_kind="documents",
        records=[{"subject": "gate pass", "sender": "[REDACTED-EMAIL]",
                  "date": "2026-07-12", "body": "driver gate pass registration"}],
    )
    load_results([make_result(), email_result], db)

    hits = search_chunks(db, "how much do we owe Gulf Office Supplies", k=1)
    assert hits[0]["source_file"] == "invoice_001.pdf"


def test_rag_answer_extractive_mode_cites_sources(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = tmp_path / "test.duckdb"
    load_results([make_result()], db)

    result = answer("what is the total of invoice INV-2026-001", str(db))
    assert result["mode"] == "extractive"
    assert "invoice_001.pdf" in result["sources"]
    assert "4520" in result["answer"]


def test_load_is_idempotent_on_rerun(tmp_path):
    # Re-processing the same file must replace its rows, not duplicate them.
    db = tmp_path / "test.duckdb"
    load_results([make_result()], db)
    load_results([make_result()], db)

    con = duckdb.connect(str(db), read_only=True)
    invoices = con.execute("SELECT count(*) FROM invoices").fetchone()[0]
    chunks = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
    con.close()
    assert invoices == 1  # not 2
    assert chunks == 1
