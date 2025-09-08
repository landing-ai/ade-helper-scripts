"""
metrics.py
----------
Defines the Metrics class to track performance and throughput of the ADE → Snowflake pipeline.

Core responsibilities:
- Record wall-clock duration using `.start()` and `.stop()`
- Track successful and failed document counts
- Track total page count processed
- Accumulate total parsing time
- Compute derived averages (e.g., seconds per page, per document)

Usage:
- Create a `Metrics` instance at the start of a pipeline run
- Call `.start()` at beginning and `.stop()` at end
- Use `.mark_ok()`, `.mark_fail()`, `.mark_parse_latency()` to track stats
- Access summary properties for per-page and per-document reporting

Example:
    metrics = Metrics()
    metrics.start()
    ...
    metrics.mark_ok()
    metrics.mark_parse_latency(3.5)
    ...
    metrics.stop()
    print(metrics.avg_wall_s_per_doc)
"""

import time
from dataclasses import dataclass


@dataclass
class Metrics:
    """
    Metrics object to track performance of a document processing pipeline.

    Use `.start()` and `.stop()` to record wall-clock timing.
    Then update parse latency and page counts incrementally.
    """

    files_ok: int = 0
    files_failed: int = 0
    pages_total: int = 0

    parse_seconds: float = 0.0
    copy_seconds: float = 0.0

    run_id: str | None = None

    _t0: float | None = None  # Wall clock start
    _t1: float | None = None  # Wall clock end

    # ----------------------------
    # Lifecycle
    # ----------------------------

    def start(self):
        """Mark the start of wall-clock timing."""
        self._t0 = time.perf_counter()
        self._t1 = None

    def stop(self):
        """Mark the end of wall-clock timing."""
        self._t1 = time.perf_counter()

    # ----------------------------
    # Update Counters
    # ----------------------------

    def mark_ok(self):
        """Increment successful file count."""
        self.files_ok += 1

    def mark_fail(self):
        """Increment failed file count."""
        self.files_failed += 1

    def mark_parse_latency(self, seconds: float):
        """Add time spent parsing a file (or doc)."""
        self.parse_seconds += float(seconds)

    # ----------------------------
    # Properties
    # ----------------------------

    @property
    def files_total(self) -> int:
        """Total number of files processed (ok + failed)."""
        return self.files_ok + self.files_failed

    @property
    def wall_seconds(self) -> float:
        """Wall-clock duration in seconds."""
        if self._t0 is None:
            return 0.0
        end = self._t1 if self._t1 is not None else time.perf_counter()
        return max(0.0, end - self._t0)

    # -------- Per-page averages --------

    @property
    def avg_parse_s_per_page(self) -> float:
        """Average parse time per page (based on parse_seconds)."""
        return (self.parse_seconds / self.pages_total) if self.pages_total else 0.0

    @property
    def avg_pipeline_s_per_page(self) -> float:
        """Average total processing time (parse + copy) per page."""
        total = self.parse_seconds + self.copy_seconds
        return (total / self.pages_total) if self.pages_total else 0.0

    @property
    def avg_wall_s_per_page(self) -> float:
        """Average wall clock time per page."""
        return (self.wall_seconds / self.pages_total) if self.pages_total else 0.0
    
    # -------- Per-document averages --------

    @property
    def avg_parse_s_per_doc(self) -> float:
        """Average parse time per document."""
        return (self.parse_seconds / self.files_total) if self.files_total else 0.0

    @property
    def avg_pipeline_s_per_doc(self) -> float:
        """Average total processing time (parse + copy) per document."""
        total = self.parse_seconds + self.copy_seconds
        return (total / self.files_total) if self.files_total else 0.0

    @property
    def avg_wall_s_per_doc(self) -> float:
        """Average wall-clock time per document."""
        return (self.wall_seconds / self.files_total) if self.files_total else 0.0


    def summary(self) -> str:
            """Return a formatted multi-line string with key metrics."""
            return (
                f"Run ID: {self.run_id or 'N/A'}\n"
                f"Files: {self.files_ok} OK / {self.files_failed} failed / {self.files_total} total\n"
                f"Pages: {self.pages_total}\n"
                f"\n"
                f"Total times (seconds):\n"
                f"  Wall clock:   {self.wall_seconds:.2f}\n"
                f"  Parse:        {self.parse_seconds:.2f}\n"
                f"  COPY:         {self.copy_seconds:.2f}\n"
                f"\n"
                f"Avg time per PAGE (s):\n"
                f"  Parse:        {self.avg_parse_s_per_page:.3f}\n"
                f"  Pipeline:     {self.avg_pipeline_s_per_page:.3f}\n"
                f"  Wall clock:   {self.avg_wall_s_per_page:.3f}\n"
                f"\n"
                f"Avg time per DOC (s):\n"
                f"  Parse:        {self.avg_parse_s_per_doc:.3f}\n"
                f"  Pipeline:     {self.avg_pipeline_s_per_doc:.3f}\n"
                f"  Wall clock:   {self.avg_wall_s_per_doc:.3f}\n"
            )