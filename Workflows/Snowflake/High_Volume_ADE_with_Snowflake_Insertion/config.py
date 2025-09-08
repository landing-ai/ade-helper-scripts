
"""
config.py
---------
Pipeline configuration using pydantic BaseSettings.

Settings precedence (highest to lowest):

1. ✅ Values passed directly to `Settings(...)` in code or notebook
2. ✅ Environment variables (e.g., from the shell or OS)
3. ✅ Values in the `.env` file (if present and path is configured)
4. ✅ Hardcoded defaults in this class

This means:
- You can override anything inline using `Settings(foo="bar")`
- You can configure deployment or user-specific secrets via environment variables
- You can share notebook-friendly `.env` files with sensible defaults
- Anything not provided above falls back to the defaults below
"""

from pydantic_settings import BaseSettings
from typing import Set

class Settings(BaseSettings):
    # --- ADE retry and processing settings (matches .env names exactly) ---

    # This must be set in .env or environment — no default here
    VISION_AGENT_API_KEY: str 
    
    # These values are expected in `.env` and loaded automatically
    BATCH_SIZE: int = 4
    MAX_WORKERS: int = 2
    MAX_RETRIES: int = 100
    MAX_RETRY_WAIT_TIME: int = 60
    RETRY_LOGGING_STYLE: str = "log_msg"

    # --- Input folder configuration ---
    file_exts: Set[str] = {".pdf", ".png", ".jpg", ".jpeg"}

    # --- Snowflake configuration ---
    snowflake_user: str = "MACHINE_USER_2"
    snowflake_account_identifier: str = "RPWERKO-LAI_SNOW_SALES"
    private_key_file: str = "/Users/andreakropp/secure_keys/rsa_key.p8"

    role: str = "ADE_DEMOS"
    warehouse: str = "SNOWFLAKE_TUTORIALS"
    database: str = "DEMOS_ADE_FINANCE"
    snowflake_schema: str = "INVOICES"

    # === Buffering thresholds ===
    # Flush to stage and COPY if buffer has this many rows
    max_rows_per_file: int = 5000
    # Flush to stage and COPY if this many seconds pass (helps bound latency)
    max_sec_per_file: float = 3.0
    # Flush after this many files are buffered (used in streaming mode)
    copy_after_files: int = 8
    #Maximum threads for parallel document processing.
    max_threads: int = 16

    # --- Snowflake table and stage names ---
    table_main: str = "INVOICES_MAIN"
    table_lines: str = "INVOICE_LINE_ITEMS"
    table_chunks: str = "PARSED_CHUNKS"
    table_markdown: str = "MARKDOWN"

    stage_ingest_name: str = "INGEST_TMP"
    stage_raw_name: str = "PARSED_INVOICES_COMPLETED"
    csv_file_format_name: str = "CSV_STD"
    json_file_format_name: str = "JSON_STD"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"