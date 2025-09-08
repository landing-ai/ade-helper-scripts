"""
row_builder.py
--------------
Transforms parsed ADE documents into structured row dictionaries.

This module defines helper functions to extract, clean, and format structured data 
from Agentic Document Extraction (ADE) outputs. It translates a parsed document 
into four categories of Snowflake-compatible rows:
  1. `main_row`: high-level invoice metadata (e.g., totals, customer, supplier)
  2. `line_rows`: individual line items or products
  3. `chunk_rows`: visual chunks with location and type metadata
  4. `markdown_record`: full parse output in JSON-compatible format (for traceability)

Core Function:
--------------
`rows_from_doc(fp, doc, run_id, sent_at, agentic_version)`:
    - Primary entry point
    - Accepts a single parsed document
    - Returns a tuple of (main_row, line_rows, chunk_rows, markdown_record, invoice_uuid)

Key Features:
-------------
• UUID generation per document to ensure traceability across tables
• Includes metadata such as run_id, file name, agentic-doc version, timestamp
• References (e.g., total_due_ref) and confidences are preserved where available
• Uses helper functions (_dig, _to_float, _first, _jsonify) for robust handling

Assumptions:
------------
• Input `doc` is the result of Agentic parsing: `doc = parse([path], extraction_model=schema)[0]`
• Field references and metadata follow ADE schema conventions
• Extraction schema class (e.g., `InvoiceExtractionSchema`) defines accessible fields

Related:
--------
• Called from `run_pipeline_streaming` (in `ade_sf_pipeline_main.py`)
• Used in conjunction with `loader.py` to populate Snowflake tables
• Complements visual grounding and ADE metadata traceability
"""

from typing import Any, Dict, List, Tuple
from datetime import datetime
import os
import uuid

from row_utils import (
    get_ltbr_page,
    _add_meta,
    _dig,
    _enum_to_str,
    _to_int,
    _to_float,
)

# ---- main adaptor: build rows from one doc ----
def rows_from_doc(
    fp: str,
    doc: Any,
    run_id: str,
    sent_at: datetime,
    agentic_version: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Returns: (main_row, line_rows, chunk_rows, markdown_record, invoice_uuid)
    """
    doc_name = os.path.basename(fp)
    invoice_uuid = str(uuid.uuid4())

    markdown = getattr(doc, "markdown", None)
    chunks = getattr(doc, "chunks", None) or []
    f = getattr(doc, "extraction", None)
    m = getattr(doc, "extraction_metadata", None)

    markdown_record = {
        "RUN_ID": run_id,
        "INVOICE_UUID": invoice_uuid,
        "DOCUMENT_NAME": doc_name,
        "SENT_AT": sent_at,
        "AGENTIC_DOC_VERSION": agentic_version,
        "MARKDOWN": markdown,
    }

    chunk_rows: List[Dict[str, Any]] = []
    for ch in chunks:
        page, l, t, r, b = get_ltbr_page(ch)
        chunk_id_obj = getattr(ch, "chunk_id", None) or getattr(ch, "id", None)
        if not chunk_id_obj:
            chunk_id_obj = f"{invoice_uuid}:{uuid.uuid4().hex[:12]}"
        ct = getattr(ch, "chunk_type", None) or getattr(ch, "type", None)

        chunk_rows.append({
            "run_id": run_id,
            "invoice_uuid": invoice_uuid,
            "document_name": doc_name,
            "chunk_id": str(chunk_id_obj),
            "chunk_type": _enum_to_str(ct),
            "text": getattr(ch, "text", None),
            "page": _to_int(page),
            "box_l": _to_float(l),
            "box_t": _to_float(t),
            "box_r": _to_float(r),
            "box_b": _to_float(b),
        })

    main_row: Dict[str, Any] = {
        "run_id": run_id,
        "invoice_uuid": invoice_uuid,
        "document_name": doc_name,
        "sent_at": sent_at,
        "agentic_doc_version": agentic_version,

        "invoice_date_raw": _dig(f, "invoice_info", "invoice_date_raw"),
        "invoice_date": _dig(f, "invoice_info", "invoice_date"),
        "invoice_number": _dig(f, "invoice_info", "invoice_number"),
        "order_date": _dig(f, "invoice_info", "order_date"),
        "po_number": _dig(f, "invoice_info", "po_number"),
        "status": _dig(f, "invoice_info", "status"),
       
        "sold_to_name": _dig(f, "customer_info", "sold_to_name"),
        "sold_to_address": _dig(f, "customer_info", "sold_to_address"),
        "customer_email": _dig(f, "customer_info", "customer_email"),

        "supplier_name": _dig(f, "company_info", "supplier_name"),
        "supplier_address": _dig(f, "company_info", "supplier_address"),
        "representative": _dig(f, "company_info", "representative"),
        "email": _dig(f, "company_info", "email"),
        "phone": _dig(f, "company_info", "phone"),
        "gstin": _dig(f, "company_info", "gstin"),
        "pan": _dig(f, "company_info", "pan"),
 
        "payment_terms": _dig(f, "order_details", "payment_terms"),
        "ship_via": _dig(f, "order_details", "ship_via"),
        "ship_date": _dig(f, "order_details", "ship_date"),
        "tracking_number": _dig(f, "order_details", "tracking_number"),

        "currency": _dig(f, "totals_summary", "currency"),
        "total_due_raw": _dig(f, "totals_summary", "total_due_raw"),
        "total_due": _dig(f, "totals_summary", "total_due"),
        "subtotal": _dig(f, "totals_summary", "subtotal"),
        "tax": _dig(f, "totals_summary", "tax"),
        "shipping": _dig(f, "totals_summary", "shipping"),
        "handling_fee": _dig(f, "totals_summary", "handling_fee"),
    }

    _add_meta(main_row, m, "company_info", "supplier_name", "supplier_name")
    _add_meta(main_row, m, "totals_summary", "total_due_raw", "total_due_raw")

    line_rows: List[Dict[str, Any]] = []
    items = _dig(f, "line_items", default=[]) or []
    for idx, li in enumerate(items):
        line_rows.append({
            "run_id": run_id,
            "invoice_uuid": invoice_uuid,
            "document_name": doc_name,
            "sent_at": sent_at,
            "agentic_doc_version": agentic_version,
            "line_index": idx,

            "line_number": _dig(li, "line_number"),
            "sku": _dig(li, "sku"),
            "description": _dig(li, "description"),
            "quantity": _dig(li, "quantity"),
            "unit_price": _dig(li, "unit_price"),
            "price": _dig(li, "price"),
            "amount": _dig(li, "amount"),
            "total": _dig(li, "total"),
        })

    return main_row, line_rows, chunk_rows, markdown_record, invoice_uuid
