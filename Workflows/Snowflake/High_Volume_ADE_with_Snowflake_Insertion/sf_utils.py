"""
sf_utils.py
-----------
Snowflake utility functions to support secure, schema-aware ingestion of 
structured extraction results from the ADE (Agentic Document Extraction) pipeline.

Includes:
- Connection management using `snowflake.connector`
- Schema-aware utilities for fully qualified table and stage naming
- Automatic table creation and format registration
- Helper functions for running DDL/DML safely via cursors

Functions:
- `sf_connect()`:
    Establishes and returns a Snowflake connection using credentials from `Settings`.

- `sfcursor()`:
    Context manager that yields a Snowflake cursor and ensures cleanup.

- `fq_table(table: str) -> str`:
    Returns the fully qualified table name based on the database, schema, and input.

- `fq_stage(stage: str) -> str`:
    Returns the fully qualified stage name for use in COPY or PUT commands.

- `ensure_formats_and_stages(settings: Settings)`:
    Ensures all required file formats and stages are created in the target schema.
    Used to initialize ingestion setup before staging and COPY operations.

Notes:
- Assumes user has proper Snowflake privileges (CREATE FILE FORMAT, CREATE STAGE, etc.)
- Integrates tightly with `Settings`, `Loader`, and the broader ingestion pipeline.

"""

from typing import Optional
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

import snowflake.connector
from cryptography.hazmat.primitives import serialization

from config import Settings


# -------------------------------
# Private Key Loading
# -------------------------------

def _load_private_key_bytes(private_key_file: str) -> bytes:
    """
    Load RSA private key from PEM file and return as DER-encoded bytes.
    """
    with open(private_key_file, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

# -------------------------------
# Snowflake Connection
# -------------------------------

def sf_connect(settings: Settings):
    """
    Create a Snowflake connection using RSA key pair authentication.
    """
    return snowflake.connector.connect(
        user=settings.snowflake_user,
        account=settings.snowflake_account_identifier,
        private_key=_load_private_key_bytes(settings.private_key_file),
        role=settings.role,
        warehouse=settings.warehouse,
        database=settings.database,
        schema=settings.snowflake_schema,
        client_session_keep_alive=True,
    )


# -------------------------------
# Cursor Context Manager
# -------------------------------

@contextmanager
def sfcursor(conn=None, settings: Optional[Settings] = None):
    """
    Yield a Snowflake cursor with optional connection ownership.

    If `conn` is not provided, one will be created using the settings.
    The connection will be closed automatically if owned by this context.
    """
    owned = False
    if conn is None:
        if settings is None:
            raise ValueError("Provide `settings` if no connection is passed to sfcursor()")
        conn = sf_connect(settings)
        owned = True
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        if owned:
            conn.close()


# -------------------------------
# Naming Helpers
# -------------------------------

def fq_table(settings: Settings, short: str) -> str:
    """
    Return fully-qualified table name in form: <DB>.<SCHEMA>.<TABLE>
    """
    return f"{settings.database}.{settings.snowflake_schema}.{short}"


def fq_stage(settings: Settings, short: str) -> str:
    """
    Return fully-qualified stage name usable in COPY statements.
    Form: @"<DB>"."<SCHEMA>"."<STAGE>"
    (quoted form is required for Snowflake stage referencing)
    """
    return f'@"{settings.database}"."{settings.snowflake_schema}"."{short}"'


# -------------------------------
# Stage and File Format Setup
# -------------------------------

def ensure_formats_and_stages(settings: Settings):
    """
    Create required file formats and ingest stage in Snowflake if they don't exist.

    This includes:
    - CSV file format (quoted, no header skip)
    - JSON file format (no strip outer array)
    - ingest stage (e.g., PARSED_INVOICES_COMPLETED)
    """
    csv_fmt = settings.csv_file_format_name
    json_fmt = settings.json_file_format_name
    ingest_stage = settings.stage_ingest_name

    with sfcursor(settings=settings) as cur:
        cur.execute(
            f"CREATE FILE FORMAT IF NOT EXISTS {csv_fmt} "
            f"TYPE=CSV FIELD_DELIMITER=',' SKIP_HEADER=0 "
            f"FIELD_OPTIONALLY_ENCLOSED_BY='\"' NULL_IF=('')"
        )
        cur.execute(
            f"CREATE FILE FORMAT IF NOT EXISTS {json_fmt} "
            f"TYPE=JSON STRIP_OUTER_ARRAY=FALSE"
        )
        cur.execute(f"CREATE STAGE IF NOT EXISTS {ingest_stage}")


def put_original_to_raw_stage(local_path: str, settings: Settings, conn=None):
    """
    Upload the original local document to the 'raw' stage for archival,
    organizing by date partition (e.g., .../date=2025-09-02).

    Args:
        local_path (str): Local file path to upload.
        settings (Settings): Settings object with stage info.
        conn: Optional existing Snowflake connection; will open one if not provided.
    """
    if not getattr(settings, "stage_raw_name", None):
        return

    date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stage = fq_stage(settings, settings.stage_raw_name)
    dest_prefix = f"{stage}/date={date_part}"
    local_uri = "file://" + Path(local_path).resolve().as_posix()

    with sfcursor(conn, settings) as cur:
        cur.execute(f"PUT '{local_uri}' {dest_prefix} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")