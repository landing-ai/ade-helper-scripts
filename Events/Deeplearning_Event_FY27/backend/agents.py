"""
Hierarchical agent pipeline for loan origination — built on Google ADK.

Architecture:
                    ManagerAgent  (LlmAgent — Claude)
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ParseSplitAgent  ExtractionAgent  LoanDecisionAgent
  (BaseAgent—ADE)  (BaseAgent—ADE)  (LlmAgent—Claude)

Agents 1 & 2 are custom BaseAgent subclasses that drive the LandingAI ADE
API.  Agents 3 & 4 are ADK LlmAgents backed by Claude.  All four are chained
in an ADK SequentialAgent.

Inter-agent state flows through the ADK session state dict (EventActions
state_delta), which replaces the old mutable job_context approach.

Best practices implemented:
  Level 1 — Agent Level:
    • Markdown sanitisation (strip prompt-injection patterns before extract)
    • Markdown length cap (prevent context window overflow)
    • Per-field range validation after extraction
  Level 2 — Agent-to-Agent Communication:
    • Typed Pydantic handoff models (ParseHandoff, ExtractionHandoff)
    • Structured progress updates written into session state
  Level 3 — Orchestration:
    • Retry with exponential back-off on ADE API calls
    • ADK SequentialAgent guarantees ordered execution
  Level 4 — Context / Data Layer:
    • Markdown truncated at MAX_MARKDOWN_CHARS before extract
    • Field-range validation applied after extraction
"""

import sys
import os
import re
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

sys.path.insert(0, str(Path(__file__).parent.parent))

from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent, InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.anthropic_llm import AnthropicLlm

from schemas import (
    SCHEMA_PER_DOC_TYPE,
    DocType,
    ExtractionRecord,
    ParseHandoff,
    ExtractionHandoff,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_API_RETRIES    = 3
RETRY_BASE_DELAY   = 1.5
MAX_MARKDOWN_CHARS = 12_000
CURRENT_YEAR       = datetime.now().year

FIELD_RANGES = {
    "gross_pay":        (0,           500_000),
    "net_pay":          (0,           500_000),
    "balance":          (-1_000_000,  50_000_000),
    "total_investment": (0,           100_000_000),
    "changes_in_value": (-50_000_000, 50_000_000),
    "investment_year":  (1900,        CURRENT_YEAR),
}

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+a",
    r"disregard\s+(the\s+)?above",
    r"new\s+instruction[s]?\s*:",
    r"system\s*:\s*you\s+must",
    r"<\s*/?(?:system|user|assistant)\s*>",
    r"```\s*(?:system|prompt)",
]
_INJECTION_RE = re.compile(
    "|".join(_INJECTION_PATTERNS), flags=re.IGNORECASE | re.DOTALL
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _sanitise_markdown(markdown: str, source_label: str = "") -> str:
    if not markdown:
        return ""
    cleaned, n_subs = _INJECTION_RE.subn("[REDACTED]", markdown)
    if n_subs:
        logger.warning("sanitise_markdown: %d pattern(s) redacted from '%s'", n_subs, source_label)
    if len(cleaned) > MAX_MARKDOWN_CHARS:
        logger.warning("sanitise_markdown: truncated '%s' from %d to %d chars",
                       source_label, len(cleaned), MAX_MARKDOWN_CHARS)
        cleaned = cleaned[:MAX_MARKDOWN_CHARS]
    return cleaned


def _validate_field_ranges(extraction: dict, doc_type: str) -> list[str]:
    warnings: list[str] = []
    for field, value in extraction.items():
        if field not in FIELD_RANGES or not isinstance(value, (int, float)):
            continue
        lo, hi = FIELD_RANGES[field]
        if not (lo <= value <= hi):
            warnings.append(
                f"[{doc_type}] Field '{field}' value {value} outside range [{lo:,}, {hi:,}]."
            )
    return warnings


def _api_call_with_retry(fn, *args, label: str = "API call", **kwargs):
    delay = RETRY_BASE_DELAY
    last_exc: Exception | None = None
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning("%s failed (attempt %d/%d): %s — retrying in %.1fs",
                           label, attempt, MAX_API_RETRIES, exc, delay)
            if attempt < MAX_API_RETRIES:
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(f"{label} failed after {MAX_API_RETRIES} attempts: {last_exc}") from last_exc


def _get_ade_client():
    from landingai_ade import LandingAIADE
    api_key = os.getenv("VISION_AGENT_API_KEY")
    if not api_key:
        raise RuntimeError("VISION_AGENT_API_KEY not set")
    return LandingAIADE(apikey=api_key)


# ---------------------------------------------------------------------------
# Agent 1 — Parse & Split  (custom BaseAgent — drives LandingAI ADE)
# ---------------------------------------------------------------------------

class ParseSplitAgent(BaseAgent):
    """
    Parses a PDF page-by-page with LandingAI ADE, classifies each page's
    document type, and groups consecutive same-type pages into logical documents.

    Reads  from session state: pdf_path, progress_callback (optional)
    Writes to session state: split_documents, parse_result_grounding,
                              current_agent, progress_pct, status
    """

    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        from landingai_ade.lib import pydantic_to_json_schema
        from ade_utils import group_pages_by_document_type
        import asyncio

        # Skip if analysis-only run has pre-loaded extractions
        if ctx.session.state.get("skip_ade"):
            yield Event(author=self.name, actions=EventActions(state_delta={}))
            return

        pdf_path = ctx.session.state.get("pdf_path")
        if not pdf_path:
            raise ValueError("ParseSplitAgent: 'pdf_path' not found in session state.")

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                "status": "parsing",
                "current_agent": "Parse & Split Agent",
                "progress_pct": 10,
            }),
        )

        loop = asyncio.get_event_loop()
        client = _get_ade_client()
        doc_type_schema = pydantic_to_json_schema(DocType)

        with open(pdf_path, "rb") as f:
            file_bytes = f.read()

        def _do_parse():
            import io
            return client.parse(document=io.BytesIO(file_bytes), model="dpt-2-latest", split="page")

        parse_result = await loop.run_in_executor(
            None, lambda: _api_call_with_retry(_do_parse, label="parse()")
        )

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"progress_pct": 25}),
        )

        page_classifications = []
        total_pages = len(parse_result.splits)

        for i, page_split in enumerate(parse_result.splits):
            safe_md = _sanitise_markdown(page_split.markdown or "", source_label=f"page_{i}")

            def _do_classify(md=safe_md):
                return client.extract(schema=doc_type_schema, markdown=md)

            classification = await loop.run_in_executor(
                None, lambda fn=_do_classify: _api_call_with_retry(fn, label=f"classify page {i}")
            )
            doc_type = (
                classification.extraction.get("type")
                or classification.extraction.get("doc_type")
            )
            page_classifications.append({"page": i, "doc_type": doc_type, "split": page_split})

            yield Event(
                author=self.name,
                actions=EventActions(state_delta={
                    "progress_pct": 25 + int((i + 1) / total_pages * 13),
                }),
            )

        split_documents = group_pages_by_document_type(page_classifications)

        # Validate handoff
        ParseHandoff(split_documents=split_documents)

        # Serialise grounding to plain dict so it survives JSON round-trips
        grounding_plain = {}
        if hasattr(parse_result, "grounding") and parse_result.grounding:
            for chunk_id, chunk in parse_result.grounding.items():
                grounding_plain[chunk_id] = {
                    "page":       getattr(chunk, "page", None),
                    "box":        list(getattr(chunk, "box", [])),
                    "type":       getattr(chunk, "type", None),
                    "confidence": getattr(chunk, "confidence", None),
                }

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                "split_documents":     split_documents,
                "parse_result_grounding": grounding_plain,
                "progress_pct":        38,
                "status":              "parsing_done",
            }),
        )


# ---------------------------------------------------------------------------
# Agent 2 — Field Extraction  (custom BaseAgent — drives LandingAI ADE)
# ---------------------------------------------------------------------------

class FieldExtractionAgent(BaseAgent):
    """
    For each logical document from Agent 1, applies the appropriate Pydantic
    schema and extracts structured financial fields via LandingAI ADE.

    Reads  from session state: split_documents, parse_result_grounding
    Writes to session state: document_extractions, extraction_warnings,
                              current_agent, progress_pct, status
    """

    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        from landingai_ade.lib import pydantic_to_json_schema
        import asyncio

        # Skip if analysis-only run has pre-loaded extractions
        if ctx.session.state.get("skip_ade"):
            yield Event(author=self.name, actions=EventActions(state_delta={}))
            return

        split_documents = ctx.session.state.get("split_documents")
        if not split_documents:
            raise ValueError("FieldExtractionAgent: no split_documents in session state.")

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                "status": "extracting",
                "current_agent": "Field Extraction Agent",
                "progress_pct": 45,
            }),
        )

        loop = asyncio.get_event_loop()
        client = _get_ade_client()
        grounding = ctx.session.state.get("parse_result_grounding", {})

        raw_extractions: dict[str, dict] = {}
        all_warnings: list[str] = []
        total = len(split_documents)

        for idx, (doc_name, doc_info) in enumerate(split_documents.items()):
            doc_type = doc_info["doc_type"]
            schema_cls = SCHEMA_PER_DOC_TYPE.get(doc_type)
            if schema_cls is None:
                continue

            safe_md = _sanitise_markdown(doc_info.get("markdown", ""), source_label=doc_name)

            def _do_extract(md=safe_md, sc=schema_cls):
                return client.extract(schema=pydantic_to_json_schema(sc), markdown=md)

            result = await loop.run_in_executor(
                None, lambda fn=_do_extract: _api_call_with_retry(fn, label=f"extract({doc_name})")
            )

            warnings = _validate_field_ranges(result.extraction or {}, doc_type=doc_type)
            all_warnings.extend(warnings)

            # Confidence: ratio of fields with grounding references
            conf = None
            meta = result.extraction_metadata or {}
            if meta:
                with_refs = sum(1 for fm in meta.values() if isinstance(fm, dict) and fm.get("references"))
                conf = round(with_refs / len(meta), 4) if meta else None

            raw_extractions[doc_name] = {
                "doc_type":            doc_type,
                "pages":               doc_info["pages"],
                "extraction":          result.extraction or {},
                "extraction_metadata": meta,
                "confidence":          conf,
            }

            yield Event(
                author=self.name,
                actions=EventActions(state_delta={
                    "progress_pct": 45 + int((idx + 1) / total * 28),
                }),
            )

        # Validate handoff
        extraction_records = {name: ExtractionRecord(**data) for name, data in raw_extractions.items()}
        ExtractionHandoff(document_extractions=extraction_records)

        document_extractions = {name: rec.model_dump() for name, rec in extraction_records.items()}

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                "document_extractions": document_extractions,
                "extraction_warnings":  all_warnings,
                "progress_pct":         73,
                "status":               "extraction_done",
            }),
        )


# ---------------------------------------------------------------------------
# Agent 3 — Loan Decision  (LlmAgent — Claude reasons over extracted fields)
# ---------------------------------------------------------------------------

def _build_decision_instruction(ctx: InvocationContext) -> str:
    """Dynamic instruction injecting borrower data from session state."""
    state = ctx.session.state
    extractions = state.get("document_extractions", {})
    loan_amount  = state.get("loan_amount", 0)
    monthly_debt = state.get("monthly_debt", 0)
    warnings     = state.get("extraction_warnings", [])

    docs_summary = json.dumps(extractions, indent=2, default=str)
    warnings_txt = "\n".join(f"  - {w}" for w in warnings) if warnings else "  (none)"

    return f"""You are a loan underwriting decision agent. Evaluate the mortgage application below.

CRITICAL INSTRUCTIONS:
- Apply ONLY the 6 rules listed below. Do NOT invent additional rules.
- Do NOT flag issues related to document age, employment history, income sustainability, number of pay stubs, or any other concern not explicitly listed.
- The "flags" array is ONLY for Rule 2 violations (net_pay > gross_pay) and Rule 6 violations (future investment year). It must be empty [] for all other situations.
- "reasons" explains each rule outcome. "flags" is strictly for fraud/anomaly indicators from the rules below.

LOAN REQUEST:
  Loan amount:    ${loan_amount:,.2f}
  Existing monthly debt: ${monthly_debt:,.2f}/mo

EXTRACTED DOCUMENT DATA:
{docs_summary}

EXTRACTION ANOMALIES (from field-range validation — include these in flags only if they indicate Rule 2 or Rule 6 violations):
{warnings_txt}

UNDERWRITING RULES — apply exactly these 6 checks and nothing else:
1. Required documents: deny if no pay_stub OR no bank_statement present.
2. Income sanity: deny and flag if gross_pay ≤ 0 OR net_pay > gross_pay.
3. DTI check: monthly income = gross_pay × 26 ÷ 12 (bi-weekly payroll assumption).
   Monthly mortgage payment = loan_amount × [0.07/12 × (1+0.07/12)^360] / [(1+0.07/12)^360 - 1].
   Total DTI = (monthly_debt + monthly_mortgage) ÷ monthly_income. Deny if DTI > 0.43.
4. Bank balance: deny and flag if balance < $0.
5. Investment reserves: deny if total_investment < loan_amount × 0.10 (only if investment statement is present).
6. Investment year: flag (but do not deny) if investment_year > {CURRENT_YEAR}.

OUTPUT — respond with ONLY a single JSON object, no extra text before or after:
{{
  "decision": "APPROVED" or "DENIED",
  "reasons": ["one string per rule checked, showing arithmetic"],
  "flags": [],
  "dti_ratio": <calculated float, or null if gross_pay is missing>,
  "extracted_fields": {{
    "<doc_name>": {{
      "doc_type": "pay_stub" | "bank_statement" | "investment_statement",
      "pages": [<page numbers>],
      "fields": {{<all extracted key-value pairs>}},
      "confidence": <float or null>
    }}
  }}
}}
"""


_loan_decision_agent = LlmAgent(
    name="LoanDecisionAgent",
    model=AnthropicLlm(model="claude-haiku-4-5-20251001"),
    instruction=_build_decision_instruction,
    output_key="loan_decision_json",
)


# ---------------------------------------------------------------------------
# Agent 4 — Manager Review  (LlmAgent — Claude reviews Agent 3's output)
# ---------------------------------------------------------------------------

def _build_manager_instruction(ctx: InvocationContext) -> str:
    """Dynamic instruction injecting Agent 3's decision from session state."""
    state = ctx.session.state
    decision_json = state.get("loan_decision_json", "")
    extractions   = state.get("document_extractions", {})

    return f"""You are a senior loan manager agent reviewing the underwriting agent's decision.

CRITICAL INSTRUCTIONS:
- Base your review ONLY on the decision data provided below.
- Do NOT invent new flags, concerns, or denial reasons beyond what the underwriting agent reported.
- Your only job is to check arithmetic consistency and apply the 4 override conditions listed below.
- Do NOT add risk points for flags the underwriting agent didn't raise.

UNDERWRITING AGENT DECISION:
{decision_json}

FULL EXTRACTED DOCUMENT DATA:
{json.dumps(extractions, indent=2, default=str)}

RISK SCORING (0–10, based solely on dti_ratio and flags from the decision above):
- DTI 36–43%: +1 point
- DTI 43–50%: +2 points
- DTI > 50%:  +4 points
- 1 flag in the decision: +2 points
- 2+ flags in the decision: +4 points
Score ≥ 7 → CRITICAL · ≥ 4 → HIGH · ≥ 2 → MEDIUM · else LOW

OVERRIDE CONDITIONS (apply only these, in order):
1. flags list is non-empty AND decision is APPROVED → override to DENIED, escalate=true
2. No pay_stub AND no bank_statement in extracted_fields → override to DENIED, escalate=true
3. DTI between 0.38–0.43, flags is empty, investment data present, decision is DENIED → set escalate=true (do not change decision)
4. Decision is APPROVED but extracted_fields is empty → override to DENIED, escalate=true

OUTPUT — respond with ONLY a single JSON object, no extra text:
{{
  "upheld": true or false,
  "override_decision": "APPROVED" or "DENIED" or null,
  "review_notes": ["note 1", "note 2", ...],
  "risk_level": "LOW" or "MEDIUM" or "HIGH" or "CRITICAL",
  "escalate": true or false
}}
"""


_manager_review_agent = LlmAgent(
    name="ManagerReviewAgent",
    model=AnthropicLlm(model="claude-haiku-4-5-20251001"),
    instruction=_build_manager_instruction,
    output_key="manager_review_json",
)


# ---------------------------------------------------------------------------
# Progress-update wrapper — BaseAgent that flanks each sub-agent with
# status updates written into session state.
# ---------------------------------------------------------------------------

class _ProgressAgent(BaseAgent):
    """
    Thin wrapper that updates progress_pct / current_agent in session state,
    delegates to a wrapped sub-agent, then writes done status.
    """

    model_config = {"arbitrary_types_allowed": True}

    wrapped: BaseAgent
    status_before: str
    agent_label: str
    progress_before: int
    progress_after: int

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                "status":        self.status_before,
                "current_agent": self.agent_label,
                "progress_pct":  self.progress_before,
            }),
        )
        async for event in self.wrapped.run_async(ctx):
            yield event
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"progress_pct": self.progress_after}),
        )


# ---------------------------------------------------------------------------
# ADK pipeline: SequentialAgent wrapping all four stages
# ---------------------------------------------------------------------------

def build_pipeline() -> SequentialAgent:
    """
    Construct and return the ADK SequentialAgent that chains:
      1. ParseSplitAgent      (BaseAgent — LandingAI ADE)
      2. FieldExtractionAgent (BaseAgent — LandingAI ADE)
      3. LoanDecisionAgent    (LlmAgent  — Claude)
      4. ManagerReviewAgent   (LlmAgent  — Claude)
    """
    return SequentialAgent(
        name="LoanOriginationPipeline",
        sub_agents=[
            ParseSplitAgent(name="ParseSplitAgent"),
            FieldExtractionAgent(name="FieldExtractionAgent"),
            _ProgressAgent(
                name="DecisionProgress",
                wrapped=_loan_decision_agent,
                status_before="deciding",
                agent_label="Loan Decision Agent",
                progress_before=75,
                progress_after=88,
            ),
            _ProgressAgent(
                name="ManagerProgress",
                wrapped=_manager_review_agent,
                status_before="reviewing",
                agent_label="Manager Agent",
                progress_before=88,
                progress_after=100,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Result extraction helpers — parse Claude JSON responses from session state
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict:
    """Extract the first complete JSON object from an LLM response."""
    text = raw.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```.*$", "", text, flags=re.DOTALL)
    text = text.strip()
    # Find the first complete {...} block to ignore any trailing text
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("Unterminated JSON object in response")


def extract_pipeline_result(session_state: dict) -> dict:
    """
    Combine the ADK session state from all four agents into the result dict
    expected by main.py / the frontend.
    """
    loan_raw     = session_state.get("loan_decision_json", "{}")
    manager_raw  = session_state.get("manager_review_json", "{}")

    try:
        loan_result = _extract_json(loan_raw) if isinstance(loan_raw, str) else loan_raw
    except Exception as e:
        logger.error("Failed to parse loan_decision_json: %s\nraw: %s", e, loan_raw)
        loan_result = {"decision": "DENIED", "reasons": ["Parsing error"], "flags": [], "dti_ratio": None, "extracted_fields": {}}

    try:
        manager_result = _extract_json(manager_raw) if isinstance(manager_raw, str) else manager_raw
    except Exception as e:
        logger.error("Failed to parse manager_review_json: %s\nraw: %s", e, manager_raw)
        manager_result = {"upheld": True, "override_decision": None, "review_notes": ["Parsing error"], "risk_level": "HIGH", "escalate": True}

    final_decision = manager_result.get("override_decision") or loan_result.get("decision", "DENIED")

    return {
        "decision":        loan_result.get("decision", "DENIED"),
        "reasons":         loan_result.get("reasons", []),
        "flags":           loan_result.get("flags", []),
        "dti_ratio":       loan_result.get("dti_ratio"),
        "extracted_fields": loan_result.get("extracted_fields", {}),
        "manager_review":  manager_result,
        "final_decision":  final_decision,
    }


# ---------------------------------------------------------------------------
# Pipeline runner — called by main.py
# ---------------------------------------------------------------------------

async def run_pipeline(
    pdf_path: str,
    loan_amount: float,
    monthly_debt: float,
    job_context: dict,
    *,
    runner,
    user_id: str,
    session_id: str,
):
    """
    Execute the ADK SequentialAgent pipeline.

    job_context is the legacy FastAPI polling dict — we mirror ADK session
    state into it so the polling endpoints keep working unchanged.
    """
    from google.adk.runners import types

    try:
        initial_state = {
            "pdf_path":     pdf_path,
            "loan_amount":  loan_amount,
            "monthly_debt": monthly_debt,
            "status":       "queued",
            "progress_pct": 0,
            "current_agent": None,
        }

        # Seed the session with initial state
        session_service = runner.session_service
        session = await session_service.get_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        session.state.update(initial_state)
        await session_service.update_session(session=session)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Run the loan origination pipeline.")],
            ),
        ):
            # Mirror state deltas into job_context for FastAPI polling
            if event.actions and event.actions.state_delta:
                delta = event.actions.state_delta
                job_context.update(delta)

        # Final state sync
        session = await session_service.get_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        result = extract_pipeline_result(session.state)
        job_context["decision_result"] = result
        job_context["document_extractions"] = session.state.get("document_extractions", {})
        job_context["status"] = "done"
        job_context["progress_pct"] = 100

    except Exception as exc:
        job_context["status"] = "error"
        job_context["error"] = str(exc)
        raise
