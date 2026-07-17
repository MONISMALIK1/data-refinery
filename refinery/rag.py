"""Retrieval-augmented answers over the refined warehouse.

Retrieval is always local (hashed embeddings + cosine). Answering uses
Claude when a key is configured; otherwise it returns the retrieved
passages verbatim -- extractive mode -- because a wrong-but-fluent
synthetic answer is worse than an honest quote with a citation.

Only refined text is retrievable: everything in the chunks table already
passed the PII scan and quality gate, so the RAG layer cannot leak what
the pipeline quarantined.
"""
from __future__ import annotations

import os

from .warehouse import search_chunks

DEFAULT_MODEL = "claude-sonnet-5"

ANSWER_PROMPT = """Answer the question using ONLY the context passages below.
Cite the source file for every fact, like [source: file.pdf]. If the context
does not contain the answer, say so.

Question: {question}

Context:
{context}"""


def answer(question: str, db_path: str, k: int = 3) -> dict:
    hits = search_chunks(db_path, question, k=k)
    sources = sorted({h["source_file"] for h in hits})

    if os.environ.get("ANTHROPIC_API_KEY") and hits:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=os.environ.get("REFINERY_MODEL", DEFAULT_MODEL),
            temperature=0.0,
            max_tokens=1024,
        )
        context = "\n\n".join(f"[{h['source_file']}] {h['text']}" for h in hits)
        response = llm.invoke(ANSWER_PROMPT.format(question=question, context=context))
        return {"answer": response.content, "sources": sources, "hits": hits, "mode": "claude"}

    lines = [f"- {h['text']} [source: {h['source_file']}]" for h in hits]
    text = (
        "Offline extractive mode (no ANTHROPIC_API_KEY): best matching passages:\n"
        + "\n".join(lines)
        if lines
        else "No indexed content matches the question."
    )
    return {"answer": text, "sources": sources, "hits": hits, "mode": "extractive"}
