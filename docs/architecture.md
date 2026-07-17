# Architecture

## Design goals

1. **Determinism wherever a correct answer exists.** Renames, date
   formats, number formats, duplicates: code, logged, reproducible.
2. **PII cannot reach storage.** The scan is a mandatory graph stage on
   every content path, ahead of both the warehouse and the embedder.
3. **Confidence is measured, not assumed.** Every load is gated on
   extractor confidence x field completeness; below threshold means a
   human looks, not a guess loads.
4. **The graph is pure; side effects are peripheral.** Nodes transform
   state and decide. The CLI quarantines files; the warehouse module
   writes DuckDB. This split is what makes re-runs and tests trivial.

## Node walkthrough

### ingest / classify
Existence and size check, then deterministic routing by extension and
content sniff (a `.txt` becomes `email` only if it has mail headers).
Unknown types go straight to the review decision.

### profile (CSV)
Row count, columns, per-column null rates, and drift detection against
the baseline contract in `config.py`. The baseline is the pipeline's
memory of what the feed should look like.

### fix (CSV)
`fixers.py` repairs known mechanical drift: synonym-map renames
(`transaction_date -> date`), implied defaults (an `amount_aed` column
implies `currency=AED`), ISO date coercion (day-first, this is a
UAE-based pipeline), currency-string-to-float coercion, dropping
unknown columns, exact-duplicate removal. Every repair appends to
`fixes_applied`; anything unfixable appends to `unfixed_issues` and
halves the file's base confidence -- silently guessing is the one thing
this tier is not allowed to do.

### extract_pdf / extract_records (PDF)
Text via pypdf, then the injected extractor. The default
`ClaudeExtractor` uses `with_structured_output(InvoiceExtraction)`, so
the model is physically unable to return anything but the schema --
hallucinated field names or string-typed amounts fail validation at the
boundary. With no `ANTHROPIC_API_KEY` it degrades to
`RegexInvoiceExtractor`, whose confidence is the fraction of required
fields it actually found. Tests inject fakes through the same seam.

### parse_email
Plain-text mailbox exports split into messages; headers and bodies
become `documents` records.

### pii_scan
Ordered regexes (Emirates ID before phone, so an ID is never
half-matched as a phone number; a lookbehind stops reference codes like
`INV-2026-001` from false-positiving). Both the raw text and every
string field of every record are redacted in place. Findings carry only
a 4-character preview -- the full value never appears in reports or
lineage. Files with findings are flagged for quarantine: the CLI copies
the original plus a findings report into `quarantine/`, and only the
redacted content proceeds.

Why the scan sits before storage rather than at query time: a vector
index is effectively write-once. You can delete a row; you cannot
un-embed the text that produced it.

### quality_gate / decide
`score = base_confidence x completeness(required fields)`. At or above
0.75 the file loads; below, it goes to the review queue with its
reasons. The gate measures and decides -- it never repairs, because
repairs belong upstream where they are logged as fixes.

## Warehouse layer (outside the graph)

`warehouse.load_results` creates five tables: `transactions`,
`invoices`, `documents`, `chunks` (text + `DOUBLE[]` embedding), and
`lineage`. Every processed file gets a lineage row whether it loaded or
not: classification, decision, records loaded, quality score, fixes,
unfixed issues, PII types found, quarantine flag, and the full audit
trail as JSON.

Embeddings are hashed bag-of-words vectors: deterministic, zero
downloads, identical in CI. This is honestly a lexical retriever;
`embedding.py` is two functions, and swapping in a neural model touches
nothing else.

## RAG layer

`ask.py` embeds the question, retrieves top-k chunks by cosine, and
answers with Claude when a key is set -- instructed to cite a source
file for every fact. Without a key it returns the retrieved passages
verbatim with citations (extractive mode), on the principle that a
wrong-but-fluent answer is worse than an honest quote. Because only
gated, redacted content was ever embedded, the RAG layer cannot leak
what the pipeline quarantined.

## Known limitations

- One baseline contract (transactions). Real deployments have many;
  the config structure generalises but registration is manual.
- Regex PII detection has blind spots (names, addresses, free-text
  identifiers). Production would add an NER pass; the redact-before-
  store architecture would not change.
- Hashed embeddings are lexical: synonyms don't match. Swap in a
  sentence-transformer for semantic retrieval.
- Invoice extraction is single-record-per-document and does not handle
  line items or multi-page tables.
- The review queue is a decision plus lineage row, not a workflow. The
  natural upgrade is LangGraph `interrupt()` with a checkpointer.
