#!/usr/bin/env python3
"""Refine a folder of mixed files into the DuckDB warehouse.

    python refine.py demo_data/ --fresh

Every file is classified, repaired or extracted, PII-scanned, quality
gated, and either loaded (tables + vector chunks) or sent to review.
Originals containing PII are copied to the quarantine folder with a
findings report; only redacted content is stored.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from refinery import build_graph
from refinery.warehouse import lineage_report, load_results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="folder of files to refine")
    parser.add_argument("--db", default="warehouse.duckdb", help="DuckDB database path")
    parser.add_argument("--quarantine", default="quarantine", help="quarantine folder")
    parser.add_argument(
        "--fresh", action="store_true", help="delete the database first for a clean run"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.fresh and db_path.exists():
        db_path.unlink()

    graph = build_graph()
    files = sorted(
        p for p in Path(args.source).iterdir() if p.is_file() and not p.name.startswith(".")
    )
    print(f"Refining {len(files)} file(s) from {args.source}\n")

    results = [graph.invoke({"file_path": str(path)}) for path in files]

    quarantine_dir = Path(args.quarantine)
    for result in results:
        if result["decision"]["quarantine"]:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            source = Path(result["file_path"])
            shutil.copy2(source, quarantine_dir / source.name)
            (quarantine_dir / f"{source.name}.findings.json").write_text(
                json.dumps(result["pii_findings"], indent=2)
            )

    counts = load_results(results, db_path)

    for result in results:
        decision = result["decision"]
        name = Path(result["file_path"]).name
        flag = "  [PII -> quarantined]" if decision["quarantine"] else ""
        print(f"{name:34} {result['file_type']:8} {decision['action']:7} "
              f"score={decision['quality_score']:.2f}{flag}")
        for reason in decision["reasons"]:
            print(f"    - {reason}")

    print("\nWarehouse summary")
    print(f"  transactions rows: {counts['transactions']}")
    print(f"  invoices rows:     {counts['invoices']}")
    print(f"  documents rows:    {counts['documents']}")
    print(f"  vector chunks:     {counts['chunks']}")
    print(f"  review queue:      {counts['review']} file(s)")

    print("\nLineage")
    for row in lineage_report(db_path):
        source, ftype, decision_, loaded, score, pii, quarantined = row
        pii_note = f" pii={pii}" if pii else ""
        q_note = " quarantined" if quarantined else ""
        print(f"  {source:34} {ftype:8} {decision_:7} loaded={loaded} "
              f"score={score:.2f}{pii_note}{q_note}")

    print(f'\nQuery it:   duckdb {db_path} "SELECT * FROM transactions"')
    print('Ask it:     python ask.py "How much do we owe Gulf Office Supplies?"')


if __name__ == "__main__":
    main()
