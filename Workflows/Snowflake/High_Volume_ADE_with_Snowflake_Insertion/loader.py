"""
loader.py
---------
Buffered Upload and COPY Logic for ADE → Snowflake

This module manages the buffered construction, staging, and loading of structured data 
(main records, line items, chunk metadata, and markdown) from parsed ADE documents 
into Snowflake tables.

Core Responsibilities:
-----------------------
• Collect and buffer row-level data (main, lines, chunks, markdown) per document
• Write batched shards to local disk in CSV or JSONL format
• Upload shards to a Snowflake staging area using PUT
• Perform COPY INTO to load staged data into Snowflake tables
• Track file paths and COPY outcomes for observability

Key Features:
-------------
• Automatic file naming by table type, run_id, and batch index
• Per-table COPY thresholds (`copy_after_files`) to control when uploads happen
• Supports VARIANT columns (e.g., markdown) via JSONL format
• Uses Snowflake internal stages (configured via Settings object)
• Cleans up or archives original document files post-COPY (if enabled)

Usage:
------
Initialize a `Loader` with:
    - `run_id` to group all output files for a pipeline run
    - `settings` object (includes stage names, file formats, thresholds)
    - Column definitions (`cols_main`, `cols_lines`) for CSV output

Then:
    - Use `.add_main(row)`, `.add_line(row)`, `.add_chunk(row)`, or `.add_markdown(record)`
    - Call `.maybe_copy()` after each file (or manually trigger with `.copy_all()`)
    - Finalize the run by calling `.close()` to flush and copy all remaining data

Assumptions:
------------
• Tables and stages are already created in Snowflake
• Required file formats (CSV_STD, JSON_STD) are registered
• Stage names and table FQNs are provided via the `Settings` object

Related:
--------
• Used by `ade_sf_pipeline_main.py` or similar orchestrators
• Complements schema-driven extraction from Agentic Document Extraction (ADE)

"""

import os, io, csv, json, gzip, time
from pathlib import Path
from typing import Any, Dict, List

from sf_utils import sf_connect, sfcursor, fq_table, fq_stage
from config import Settings

# --- Column orders for Snowflake COPY (must match table definitions) ---

COLS_MAIN = [
    "run_id", "invoice_uuid", "document_name", "sent_at", "agentic_doc_version",
    "invoice_date_raw", "invoice_date", "invoice_number", "order_date", "po_number", "status", 
    "sold_to_name", "sold_to_address", "customer_email",
    "supplier_name",  "supplier_address", "representative", "email", "phone", "gstin", "pan",
    "payment_terms", "ship_via",  "ship_date", "tracking_number",
    "currency", "total_due_raw", "total_due", "subtotal", "tax", "shipping","handling_fee",
    "supplier_name_ref", "supplier_name_conf", "total_due_raw_ref", "total_due_raw_conf",  #metadata chunk reference and confidence score
]

COLS_LINES = [
    "run_id", "invoice_uuid", "document_name", "sent_at", "agentic_doc_version",
    "line_index", "line_number", "sku", "description", "quantity", "unit_price", "price", "amount", "total",
]

class Loader:
    """
    Buffered uploader for parsed document output.

    Buffers rows (CSV and JSONL) in memory.
    Writes to disk as .gz files when thresholds are hit.
    Stages files to Snowflake ingest stage and issues COPY commands to load tables.
    """

    def __init__(self, run_id: str, settings: Settings, cols_main: List[str], cols_lines: List[str]):
        self.run_id = run_id
        self.S = settings
        self.cols_main = cols_main
        self.cols_lines = cols_lines
        self.conn = sf_connect(settings)

        # In-memory buffers for row data
        self._main_rows = []       # rows for INVOICES_MAIN
        self._lines_rows = []      # rows for INVOICE_LINE_ITEMS
        self._chunks_jsonl = []    # rows for PARSED_CHUNKS
        self._markdown_jsonl = []  # rows for MARKDOWN

        # Track which files have been staged and are ready for COPY
        self._main_ready = []
        self._lines_ready = []
        self._chunks_ready = []
        self._markdown_ready = []

        # Track when the last file was flushed to measure duration-based flush threshold
        self._file_started = time.monotonic()

    # ---------------------------
    # Public API
    # ---------------------------

    def add_main(self, row):       self._csv_add(row, self._main_rows, self._flush_main)
    def add_line(self, row):       self._csv_add(row, self._lines_rows, self._flush_lines)
    def add_chunk(self, rec):      self._jsonl_add(rec, self._chunks_jsonl, self._flush_chunks)
    def add_markdown(self, rec):   self._jsonl_add(rec, self._markdown_jsonl, self._flush_markdown)

    def maybe_copy(self):
        """Check if buffers are large enough to COPY, and do so if ready."""
        self._copy_if_ready_all()

    def close(self):
        """Flush all remaining buffers to disk and COPY everything to Snowflake."""
        self._final_flush_and_copy()

    # ---------------------------
    # Internal helpers
    # ---------------------------

    def _hit_threshold(self) -> bool:
        """Check whether enough time has passed to force a flush."""
        return (time.monotonic() - self._file_started) >= self.S.max_sec_per_file

    def _csv_add(self, row, buf, flusher):
        """Append to a CSV buffer and flush if threshold hit."""
        buf.append(row)
        if len(buf) >= self.S.max_rows_per_file or self._hit_threshold():
            flusher()

    def _jsonl_add(self, rec, buf, flusher):
        """Append to a JSONL buffer and flush if threshold hit."""
        buf.append(rec)
        if len(buf) >= self.S.max_rows_per_file or self._hit_threshold():
            flusher()

    def _write_gz(self, content: bytes, subdir: str) -> str:
        """Write compressed .gz file to disk in staging folder."""
        local_dir = Path(f"ingest_tmp/run_id={self.run_id}/{subdir}")
        local_dir.mkdir(parents=True, exist_ok=True)
        tmp = local_dir / f"tmp{int(time.time()*1e6)}.gz"
        with open(tmp, "wb") as f:
            f.write(content)
        return str(tmp)

    def _put_and_track(self, local_path: str, subdir: str, ready_list: list[str]):
        """PUT local file to Snowflake stage and track it as ready for COPY."""
        stage_prefix = f"{fq_stage(self.S, self.S.stage_ingest_name)}/run_id={self.run_id}/{subdir}"
        local_uri = "file://" + Path(local_path).resolve().as_posix()
        with sfcursor(self.conn, self.S) as cur:
            cur.execute(f"PUT '{local_uri}' {stage_prefix} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        ready_list.append(os.path.basename(local_path))

    # ---------------------------
    # Flushers (write to .gz and PUT)
    # ---------------------------

    def _flush_main(self):
        if not self._main_rows: return
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.cols_main, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self._main_rows)
        gz = gzip.compress(output.getvalue().encode("utf-8"))
        path = self._write_gz(gz, "main")
        self._main_rows.clear()
        self._file_started = time.monotonic()
        self._put_and_track(path, "main", self._main_ready)

    def _flush_lines(self):
        if not self._lines_rows: return
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.cols_lines, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self._lines_rows)
        gz = gzip.compress(output.getvalue().encode("utf-8"))
        path = self._write_gz(gz, "lines")
        self._lines_rows.clear()
        self._file_started = time.monotonic()
        self._put_and_track(path, "lines", self._lines_ready)

    def _flush_chunks(self):
        if not self._chunks_jsonl: return
        payload = ("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in self._chunks_jsonl)).encode("utf-8")
        gz = gzip.compress(payload)
        path = self._write_gz(gz, "chunks_json")
        self._chunks_jsonl.clear()
        self._file_started = time.monotonic()
        self._put_and_track(path, "chunks_json", self._chunks_ready)

    def _flush_markdown(self):
        if not self._markdown_jsonl: return
        payload = ("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in self._markdown_jsonl)).encode("utf-8")
        gz = gzip.compress(payload)
        path = self._write_gz(gz, "markdown")
        self._markdown_jsonl.clear()
        self._file_started = time.monotonic()
        self._put_and_track(path, "markdown", self._markdown_ready)

    # ---------------------------
    # COPY logic
    # ---------------------------

    def _copy_if_ready(self, ready_list, table_short, subdir, is_csv, *, force=False):
        """
        Issue a COPY INTO <table> FROM staged files.

        Args:
            ready_list: list of filenames ready to be copied
            table_short: name of the Snowflake table
            subdir: subdir of run_id (main, lines, etc.)
            is_csv: True for CSV tables, False for JSONL
            force: if True, copy even if ready_list is empty (used in close())
        """
        stage_subdir = f"{fq_stage(self.S, self.S.stage_ingest_name)}/run_id={self.run_id}/{subdir}"
        pattern = ".*\\.gz"

        if force:
            with sfcursor(self.conn, self.S) as cur:
                cur.execute(f"LIST {stage_subdir}")
                if not cur.fetchall():
                    return
        else:
            if len(ready_list) < self.S.copy_after_files:
                return

        with sfcursor(self.conn, self.S) as cur:
            if is_csv:
                cur.execute(
                    f"COPY INTO {fq_table(self.S, table_short)} FROM {stage_subdir} "
                    f"PATTERN='{pattern}' FILE_FORMAT=(FORMAT_NAME={self.S.csv_file_format_name} SKIP_HEADER=1) "
                    f"PURGE=TRUE ON_ERROR=ABORT_STATEMENT"
                )
            else:
                cur.execute(
                    f"COPY INTO {fq_table(self.S, table_short)} FROM {stage_subdir} "
                    f"PATTERN='{pattern}' FILE_FORMAT=(FORMAT_NAME={self.S.json_file_format_name}) "
                    f"MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE PURGE=TRUE ON_ERROR=ABORT_STATEMENT"
                )

        ready_list.clear()

    def _copy_if_ready_all(self):
        """Attempt COPY for all 4 table types."""
        self._copy_if_ready(self._main_ready,    self.S.table_main,    "main",        True)
        self._copy_if_ready(self._lines_ready,   self.S.table_lines,   "lines",       True)
        self._copy_if_ready(self._chunks_ready,  self.S.table_chunks,  "chunks_json", False)
        self._copy_if_ready(self._markdown_ready,self.S.table_markdown,"markdown",    False)

    def _final_flush_and_copy(self):
        """Flush all buffers and issue COPY commands (force=True)."""
        self._flush_main()
        self._flush_lines()
        self._flush_chunks()
        self._flush_markdown()

        self._copy_if_ready(self._main_ready,    self.S.table_main,    "main",        True, force=True)
        self._copy_if_ready(self._lines_ready,   self.S.table_lines,   "lines",       True, force=True)
        self._copy_if_ready(self._chunks_ready,  self.S.table_chunks,  "chunks_json", False, force=True)
        self._copy_if_ready(self._markdown_ready,self.S.table_markdown,"markdown",    False, force=True)

        self.conn.close()