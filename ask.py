#!/usr/bin/env python3
"""Ask a question over the refined warehouse (RAG).

    python ask.py "How much do we owe Gulf Office Supplies and when is it due?"

Retrieval is local; answering uses Claude when ANTHROPIC_API_KEY is set
and falls back to extractive quotes with citations when it is not.
"""
from __future__ import annotations

import argparse

from refinery.rag import answer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--db", default="warehouse.duckdb")
    parser.add_argument("--k", type=int, default=3, help="passages to retrieve")
    args = parser.parse_args()

    result = answer(args.question, args.db, k=args.k)
    print(f"[mode: {result['mode']}]\n")
    print(result["answer"])
    if result["sources"]:
        print("\nSources: " + ", ".join(result["sources"]))


if __name__ == "__main__":
    main()
