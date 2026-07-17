"""Deterministic repairs for known, mechanical schema drift.

This is the tier that keeps the LLM out of the hot path: renamed
columns, regional date formats, currency-formatted numbers, and exact
duplicates are all repairs with one correct answer, so they are code,
not prompts. Every repair is logged; anything this module cannot fix is
reported as an unfixed issue and lowers the file's confidence instead of
being silently guessed.
"""
from __future__ import annotations

import re
from datetime import datetime

# Day-first formats before month-first: this pipeline's feeds are UAE-based.
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y"]


def coerce_date(value: str) -> str | None:
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def coerce_number(value) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if not cleaned or cleaned in {".", "-", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def fix_rows(rows: list[dict], baseline: dict) -> tuple[list[dict], list[str], list[str]]:
    """Repair drifted rows against the baseline contract.

    Returns (fixed_rows, fixes_applied, unfixed_issues).
    """
    fixes: list[str] = []
    unfixed: list[str] = []
    if not rows:
        return [], fixes, ["file contains no data rows"]

    observed = list(rows[0].keys())
    synonyms = baseline["synonyms"]

    # 1. Undo known renames.
    rename_map = {col: synonyms[col.lower()] for col in observed if col.lower() in synonyms}
    if rename_map:
        rows = [{rename_map.get(k, k): v for k, v in r.items()} for r in rows]
        for old, new in sorted(rename_map.items()):
            fixes.append(f"renamed column '{old}' -> '{new}'")

    # 2. A rename like amount_aed implies the missing currency.
    implied_defaults = dict(baseline.get("defaults", {}))
    for old_col, currency in baseline.get("currency_implying_columns", {}).items():
        if old_col in (c.lower() for c in observed):
            implied_defaults["currency"] = currency

    # 3. Fill missing columns that have defaults; report the rest.
    present = set(rows[0].keys())
    for col in baseline["columns"]:
        if col in present:
            continue
        if col in implied_defaults:
            for r in rows:
                r[col] = implied_defaults[col]
            fixes.append(f"filled missing column '{col}' with default '{implied_defaults[col]}'")
        else:
            unfixed.append(f"missing required column '{col}' with no known default")

    # 4. Drop columns the contract does not know.
    extra = [c for c in rows[0] if c not in baseline["columns"]]
    if extra:
        rows = [{k: v for k, v in r.items() if k not in extra} for r in rows]
        fixes.append(f"dropped unexpected column(s): {', '.join(sorted(extra))}")

    # 5. Coerce dates to ISO.
    for col in baseline["date_columns"]:
        if col not in rows[0]:
            continue
        converted = 0
        for r in rows:
            original = str(r.get(col) or "")
            iso = coerce_date(original)
            if iso is None:
                unfixed.append(f"unparseable date '{original}' in column '{col}'")
            elif iso != original:
                r[col] = iso
                converted += 1
        if converted:
            fixes.append(f"normalised {converted} value(s) in '{col}' to ISO dates")

    # 6. Coerce numbers ("1,200.50", "AED 950") to floats.
    for col in baseline["numeric_columns"]:
        if col not in rows[0]:
            continue
        converted = 0
        for r in rows:
            original = r.get(col)
            number = coerce_number(original)
            if number is None:
                unfixed.append(f"unparseable number '{original}' in column '{col}'")
            else:
                if str(original) != str(number):
                    converted += 1
                r[col] = number
        if converted:
            fixes.append(f"coerced {converted} value(s) in '{col}' to numeric")

    # 7. Drop exact duplicate rows.
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for r in rows:
        key = tuple(sorted((k, str(v)) for k, v in r.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    if len(deduped) < len(rows):
        fixes.append(f"dropped {len(rows) - len(deduped)} exact duplicate row(s)")

    return deduped, fixes, unfixed
