"""LangGraph pipeline assembly.

One file in, one decision out. The graph is pure -- no database writes,
no file moves -- so it can be re-run, tested, and reasoned about; all
side effects live in the CLI and warehouse layers.

    ingest -> classify --(csv)---> profile_csv -> fix_csv ----\\
                       --(pdf)---> extract_pdf -> extract_records -> pii_scan -> quality_gate -> decide
                       --(email)-> parse_email ---------------/
                       --(unknown) -----------------------------------------------------------> decide

The PII scan is unconditional for every content path: nothing reaches
the quality gate, the warehouse, or the vector index unredacted.
"""
from __future__ import annotations

import operator
from pathlib import Path
from typing import Annotated, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .classify import classify_file
from .config import TRANSACTIONS_BASELINE
from .extract import ClaudeExtractor, extract_pdf_text, parse_email_export
from .fixers import fix_rows
from .pii import redact_records, scan_and_redact
from .profiling import detect_drift, load_csv, profile_rows
from .quality import gate


class RefineryState(TypedDict, total=False):
    file_path: str
    file_type: str
    raw_text: str
    rows: list
    profile: dict
    drift: dict
    fixes_applied: list
    unfixed_issues: list
    records: list
    record_kind: str
    extraction_method: str
    base_confidence: float
    pii_findings: list
    quality_score: float
    decision: dict
    audit_trail: Annotated[list, operator.add]


ExtractorFn = Callable[[dict], dict]


def build_graph(extractor: Optional[ExtractorFn] = None, checkpointer=None):
    """Compile the refinery graph. ``extractor`` handles unstructured
    documents and defaults to :class:`ClaudeExtractor` (which itself
    degrades to regex parsing without an API key); tests inject fakes."""
    extractor = extractor if extractor is not None else ClaudeExtractor()

    def ingest(state: RefineryState) -> dict:
        path = Path(state["file_path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        return {
            "fixes_applied": [],
            "unfixed_issues": [],
            "records": [],
            "pii_findings": [],
            "base_confidence": 0.0,
            "audit_trail": [f"ingest: {path.name} ({path.stat().st_size} bytes)"],
        }

    def classify(state: RefineryState) -> dict:
        file_type = classify_file(state["file_path"])
        return {"file_type": file_type, "audit_trail": [f"classify: {file_type}"]}

    def route(state: RefineryState) -> str:
        return state["file_type"] if state["file_type"] in ("csv", "pdf", "email") else "unknown"

    # --- CSV path --------------------------------------------------------
    def profile_csv(state: RefineryState) -> dict:
        rows = load_csv(state["file_path"])
        profile = profile_rows(rows)
        drift = detect_drift(profile["columns"], TRANSACTIONS_BASELINE)
        note = (
            f"profile: {profile['row_count']} rows, drift detected "
            f"(missing={drift['missing_columns']}, unexpected={drift['unexpected_columns']})"
            if drift["has_drift"]
            else f"profile: {profile['row_count']} rows, schema matches baseline"
        )
        return {"rows": rows, "profile": profile, "drift": drift, "audit_trail": [note]}

    def fix_csv(state: RefineryState) -> dict:
        if not state["drift"]["has_drift"]:
            return {
                "records": state["rows"],
                "record_kind": "transactions",
                "base_confidence": 1.0,
                "extraction_method": "csv",
                "audit_trail": ["fix: no repairs needed"],
            }
        fixed, fixes, unfixed = fix_rows(state["rows"], TRANSACTIONS_BASELINE)
        return {
            "records": fixed,
            "record_kind": "transactions",
            "fixes_applied": fixes,
            "unfixed_issues": unfixed,
            "base_confidence": 1.0 if not unfixed else 0.5,
            "extraction_method": "csv+fixers",
            "audit_trail": [f"fix: {len(fixes)} repair(s), {len(unfixed)} unfixed issue(s)"],
        }

    # --- PDF path --------------------------------------------------------
    def extract_pdf(state: RefineryState) -> dict:
        text = extract_pdf_text(state["file_path"])
        return {"raw_text": text, "audit_trail": [f"extract_pdf: {len(text)} chars of text"]}

    def extract_records(state: RefineryState) -> dict:
        result = extractor(dict(state))
        return {
            "records": result["records"],
            "record_kind": "invoices",
            "base_confidence": result["confidence"],
            "extraction_method": result["method"],
            "audit_trail": [
                f"extract_records: {len(result['records'])} record(s) via "
                f"{result['method']}, confidence={result['confidence']:.2f}"
            ],
        }

    # --- Email path ------------------------------------------------------
    def parse_email(state: RefineryState) -> dict:
        text = Path(state["file_path"]).read_text(encoding="utf-8", errors="ignore")
        emails = parse_email_export(text)
        return {
            "raw_text": text,
            "records": emails,
            "record_kind": "documents",
            "base_confidence": 1.0,
            "extraction_method": "email_parser",
            "audit_trail": [f"parse_email: {len(emails)} message(s)"],
        }

    # --- Common tail -----------------------------------------------------
    def pii_scan(state: RefineryState) -> dict:
        findings: list = []
        update: dict = {}
        if state.get("raw_text"):
            redacted_text, found = scan_and_redact(state["raw_text"])
            update["raw_text"] = redacted_text
            findings.extend(found)
        redacted_records, found = redact_records(state.get("records", []))
        update["records"] = redacted_records
        findings.extend(found)
        types = sorted({f["type"] for f in findings})
        update["pii_findings"] = findings
        update["audit_trail"] = [
            f"pii_scan: {len(findings)} finding(s)" + (f" [{', '.join(types)}]" if types else "")
        ]
        return update

    def quality_gate(state: RefineryState) -> dict:
        score, verdict = gate(
            state.get("records", []), state.get("record_kind", ""), state["base_confidence"]
        )
        return {
            "quality_score": score,
            "audit_trail": [f"quality_gate: score={score:.2f} -> {verdict}"],
        }

    def decide(state: RefineryState) -> dict:
        reasons: list[str] = []
        if state["file_type"] not in ("csv", "pdf", "email"):
            action, score = "REVIEW", 0.0
            reasons.append("unclassified file type; needs a human to route it")
        else:
            score = state["quality_score"]
            action = "LOAD" if score >= 0.75 else "REVIEW"
            reasons.extend(state.get("fixes_applied", []))
            reasons.extend(f"UNFIXED: {issue}" for issue in state.get("unfixed_issues", []))
            if state.get("pii_findings"):
                types = sorted({f["type"] for f in state["pii_findings"]})
                reasons.append(
                    f"PII redacted before load ({', '.join(types)}); original quarantined"
                )
        decision = {
            "action": action,
            "quality_score": score,
            "quarantine": bool(state.get("pii_findings")),
            "reasons": reasons,
        }
        return {
            "decision": decision,
            "audit_trail": [f"decide: {action} (score={score:.2f})"],
        }

    graph = StateGraph(RefineryState)
    graph.add_node("ingest", ingest)
    graph.add_node("classify", classify)
    graph.add_node("profile_csv", profile_csv)
    graph.add_node("fix_csv", fix_csv)
    graph.add_node("extract_pdf", extract_pdf)
    graph.add_node("extract_records", extract_records)
    graph.add_node("parse_email", parse_email)
    graph.add_node("pii_scan", pii_scan)
    graph.add_node("quality_gate", quality_gate)
    graph.add_node("decide", decide)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "classify")
    graph.add_conditional_edges(
        "classify",
        route,
        {
            "csv": "profile_csv",
            "pdf": "extract_pdf",
            "email": "parse_email",
            "unknown": "decide",
        },
    )
    graph.add_edge("profile_csv", "fix_csv")
    graph.add_edge("fix_csv", "pii_scan")
    graph.add_edge("extract_pdf", "extract_records")
    graph.add_edge("extract_records", "pii_scan")
    graph.add_edge("parse_email", "pii_scan")
    graph.add_edge("pii_scan", "quality_gate")
    graph.add_edge("quality_gate", "decide")
    graph.add_edge("decide", END)

    return graph.compile(checkpointer=checkpointer)
