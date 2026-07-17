#!/usr/bin/env python3
"""Regenerate the demo invoice PDFs (dev-only; needs fpdf2).

The CSVs and email export are plain text and live in demo_data/ directly;
only the PDFs need generating. Run from the repo root:

    python scripts/make_demo_data.py
"""
from pathlib import Path

from fpdf import FPDF

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo_data"

INVOICES = {
    "invoice_001.pdf": [
        "INVOICE",
        "Invoice Number: INV-2026-001",
        "Vendor: Gulf Office Supplies LLC",
        "Invoice Date: 2026-07-01",
        "Due Date: 2026-08-01",
        "Items: Office chairs x 8, Standing desks x 4",
        "Total: AED 4,520.00",
    ],
    "invoice_002.pdf": [
        "INVOICE",
        "Invoice Number: INV-2026-002",
        "Vendor: DXB Logistics FZE",
        "Invoice Date: 2026-07-05",
        "Due Date: 2026-08-05",
        "Contact: +971 50 123 4567",
        "Items: Freight forwarding, June 2026",
        "Total: AED 12,750.00",
    ],
    # Deliberately incomplete: no total and no due date, so the quality
    # gate routes it to human review in the demo.
    "invoice_003.pdf": [
        "INVOICE",
        "Invoice Number: INV-2026-003",
        "Vendor: Creek Marketing Agency",
        "Invoice Date: 2026-07-08",
        "Note: Amount to be confirmed after scope review.",
    ],
}


def main() -> None:
    DEMO_DIR.mkdir(exist_ok=True)
    for name, lines in INVOICES.items():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", size=12)
        for line in lines:
            pdf.cell(0, 9, line, new_x="LMARGIN", new_y="NEXT")
        pdf.output(str(DEMO_DIR / name))
        print(f"wrote {DEMO_DIR / name}")


if __name__ == "__main__":
    main()
