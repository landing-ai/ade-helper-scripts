
"""
doc_utils.py
------------
Utilities for document-level metadata and page counting used in the ADE → Snowflake pipeline.

Key Functions:
- `get_doc_pages(doc)`: Safely extract the number of pages in a parsed document.
    - Falls back to 1 if page count is unavailable or malformed.
    - Ensures accurate metrics reporting during pipeline runs.

Intended for use in:
- Metrics aggregation (e.g., pages per document)
- Logging and diagnostics
- Runtime safeguards for edge cases (e.g., image-only or malformed docs)

Example:
    from doc_utils import get_doc_pages
    pages = get_doc_pages(parsed_doc)
"""

from typing import Any, Optional


def _coerce_int(x: Any) -> Optional[int]:
    """
    Convert a value to an int if possible, else return None.
    Useful for fields that may be None, strings, or invalid types.
    """
    try:
        return None if x is None else int(x)
    except Exception:
        return None


def get_doc_pages(doc: Any) -> int:
    """
    Return the number of pages in a parsed document.
    Returns the maximum value found, or 0 if none are valid.
    """
    return max(
        (g.page for chunk in doc.chunks for g in (chunk.grounding or [])),
        default=0
        ) + 1  # Pages are 0-indexed, so +1 gives total count
