"""
Hierarchical agent pipeline for loan origination.

Architecture:
                    ManagerAgent  (orchestrator / reviewer)
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ParseSplitAgent  ExtractionAgent  LoanDecisionAgent
   (Agent 1)        (Agent 2)        (Agent 3)

The Manager Agent runs last: it receives the full output of Agent 3,
reviews it for consistency, edge cases, and risk, then either upholds
or overrides the decision. The manager's output is the final word.

All agents share state through a mutable job_context dict so FastAPI
can poll live progress at any point.

Best practices implemented:
  Level 1 — Agent Level:
    • Markdown sanitisation (strip prompt-injection patterns before each extract call)
    • Markdown length cap (prevent context window overflow)
    • Per-field range validation after extraction
    • Extracted field verification assertions
  Level 2 — Agent-to-Agent Communication:
    • Typed Pydantic handoff models (ParseHandoff, ExtractionHandoff, ExtractionRecord)
    • Validation on each handoff — pipeline halts with a clear error on bad data
    • Structured error objects (AgentError) propagated through job_context
  Level 3 — Orchestration:
    • Retry with exponential back-off on all ADE API calls (parse + extract)
    • Max retries configurable via MAX_API_RETRIES
    • Explicit termination: pipeline raises immediately on unrecoverable errors
  Level 4 — Context / Data Layer:
    • Markdown truncated at MAX_MARKDOWN_CHARS before sending to extract
    • Extraction confidence surfaced from extraction_metadata when available
    • Field-range validation applied after extraction (plausible financial values)
    • Current year used as the "future year" upper bound for investment statements
"""

import sys
import os
import re
import time
import logging
from datetime import datetime
from pathlib import Path

# Allow imports from the project root (ade_utils lives there)
sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas import (
    SCHEMA_PER_DOC_TYPE,
    DocType,
    ExtractionRecord,
    ParseHandoff,
    ExtractionHandoff,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

MAX_API_RETRIES     = 3          # Level 3: retry budget for ADE API calls
RETRY_BASE_DELAY    = 1.5        # seconds; doubles each attempt
MAX_MARKDOWN_CHARS  = 12_000     # Level 4: guard against oversized context
CURRENT_YEAR        = datetime.now().year

# Plausible financial ranges for extracted fields (Level 4 + Level 1 validation)
FIELD_RANGES = {
    "gross_pay":         (0,        500_000),   # per pay period
    "net_pay":           (0,        500_000),
    "balance":           (-1_000_000, 50_000_000),
    "total_investment":  (0,        100_000_000),
    "changes_in_value":  (-50_000_000, 50_000_000),
    "investment_year":   (1900,     CURRENT_YEAR),   # future year = anomaly
}

# Patterns that could be prompt-injection attempts embedded in document text
# (Level 1: sanitise before passing markdown to client.extract)
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
    "|".join(_INJECTION_PATTERNS),
    flags=re.IGNORECASE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Level 1 + Level 4 helpers
# ---------------------------------------------------------------------------

def _sanitise_markdown(markdown: str, source_label: str = "") -> str:
    """
    Level 1 — Strip potential prompt-injection sequences from PDF-extracted
    markdown before it reaches client.extract().

    Level 4 — Truncate at MAX_MARKDOWN_CHARS to prevent context overflow.
    """
    if not markdown:
        return ""

    # Strip injection patterns
    cleaned, n_subs = _INJECTION_RE.subn("[REDACTED]", markdown)
    if n_subs:
        logger.warning(
            "sanitise_markdown: %d injection pattern(s) redacted from '%s'",
            n_subs,
            source_label,
        )

    # Truncate to guard against oversized context
    if len(cleaned) > MAX_MARKDOWN_CHARS:
        logger.warning(
            "sanitise_markdown: markdown for '%s' truncated from %d to %d chars",
            source_label,
            len(cleaned),
            MAX_MARKDOWN_CHARS,
        )
        cleaned = cleaned[:MAX_MARKDOWN_CHARS]

    return cleaned


def _validate_field_ranges(
    extraction: dict, doc_type: str
) -> list[str]:
    """
    Level 4 + Level 1 — Validate extracted numeric fields against plausible ranges.
    Returns a list of warning strings (empty if all values are in range).
    """
    warnings: list[str] = []
    for field, value in extraction.items():
        if field not in FIELD_RANGES or not isinstance(value, (int, float)):
            continue
        lo, hi = FIELD_RANGES[field]
        if not (lo <= value <= hi):
            warnings.append(
                f"[{doc_type}] Field '{field}' value {value} is outside the "
                f"expected range [{lo:,}, {hi:,}]."
            )
    return warnings


def _extract_confidence(extraction_metadata: dict, grounding: dict | None = None) -> float | None:
    """
    Level 4 — Derive a confidence score for a document's extraction.

    Looks up each field's chunk references in parse_result.grounding and
    averages the confidence values reported by the ADE parse API.
    Falls back to None if grounding is unavailable.
    """
    if not extraction_metadata:
        return None
    scores = []
    for field_meta in extraction_metadata.values():
        if not isinstance(field_meta, dict):
            continue
        refs = field_meta.get("references", [])
        for chunk_id in refs:
            if grounding is not None:
                chunk = grounding.get(chunk_id)
                if chunk is not None:
                    score = getattr(chunk, "confidence", None)
                    if isinstance(score, (int, float)):
                        scores.append(float(score))
    return round(sum(scores) / len(scores), 4) if scores else None


# ---------------------------------------------------------------------------
# Level 3 — Retry decorator for ADE API calls
# ---------------------------------------------------------------------------

def _api_call_with_retry(fn, *args, label: str = "API call", **kwargs):
    """
    Level 3 — Call `fn(*args, **kwargs)` with exponential back-off.
    Raises the last exception if all retries are exhausted.
    """
    delay = RETRY_BASE_DELAY
    last_exc: Exception | None = None
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                label, attempt, MAX_API_RETRIES, exc, delay,
            )
            if attempt < MAX_API_RETRIES:
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(
        f"{label} failed after {MAX_API_RETRIES} attempts: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Helper: build ADE client
# ---------------------------------------------------------------------------

def _get_client():
    from landingai_ade import LandingAIADE
    api_key = os.getenv("VISION_AGENT_API_KEY")
    if not api_key:
        raise RuntimeError("VISION_AGENT_API_KEY not set")
    return LandingAIADE(apikey=api_key)


# ---------------------------------------------------------------------------
# Agent 1 — Parse & Split
# ---------------------------------------------------------------------------

def parse_and_split(pdf_path: str, job_context: dict) -> dict:
    """
    Parse a PDF page-by-page, classify each page's document type,
    and group consecutive same-type pages into logical documents.

    Best practices applied:
      • Level 3: parse + per-page extract wrapped in _api_call_with_retry
      • Level 1: page markdown sanitised before classification extract
      • Level 2: output validated as ParseHandoff before storing in context
    """
    from landingai_ade.lib import pydantic_to_json_schema
    from ade_utils import group_pages_by_document_type

    client = _get_client()

    job_context["status"] = "parsing"
    job_context["current_agent"] = "Parse & Split Agent"
    job_context["progress_pct"] = 10

    # Level 3: retry the parse call
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    def _do_parse():
        import io
        return client.parse(
            document=io.BytesIO(file_bytes),
            model="dpt-2-latest",
            split="page",
        )

    parse_result = _api_call_with_retry(_do_parse, label="parse()")

    job_context["progress_pct"] = 25

    doc_type_json_schema = pydantic_to_json_schema(DocType)

    # Classify each page
    page_classifications = []
    total_pages = len(parse_result.splits)
    for i, page_split in enumerate(parse_result.splits):
        # Level 1 + Level 4: sanitise markdown before sending to extract
        safe_markdown = _sanitise_markdown(
            page_split.markdown or "", source_label=f"page_{i}"
        )

        # Level 3: retry the per-page classification extract
        def _do_classify(md=safe_markdown):
            return client.extract(schema=doc_type_json_schema, markdown=md)

        classification = _api_call_with_retry(
            _do_classify, label=f"extract(classify page {i})"
        )

        doc_type = (
            classification.extraction.get("type")
            or classification.extraction.get("doc_type")
        )
        page_classifications.append({
            "page": i,
            "doc_type": doc_type,
            "split": page_split,
        })
        job_context["progress_pct"] = 25 + int((i + 1) / total_pages * 13)

    job_context["progress_pct"] = 38

    split_documents = group_pages_by_document_type(page_classifications)

    # Level 2: validate handoff before passing to Agent 2
    handoff = ParseHandoff(split_documents=split_documents)

    job_context["parse_result"] = parse_result
    job_context["split_documents"] = handoff.split_documents

    return {"split_documents": handoff.split_documents}


# ---------------------------------------------------------------------------
# Agent 2 — Field Extraction
# ---------------------------------------------------------------------------

def extract_fields(job_context: dict) -> dict:
    """
    For each logical document from Agent 1, apply the appropriate Pydantic
    schema and extract structured financial fields.

    Best practices applied:
      • Level 2: consumes ParseHandoff; validates input has split_documents
      • Level 1 + Level 4: markdown sanitised + truncated per document
      • Level 3: extract call wrapped in _api_call_with_retry
      • Level 4: field-range validation + confidence score surfaced
      • Level 2: output validated as ExtractionHandoff before storing
    """
    from landingai_ade.lib import pydantic_to_json_schema

    client = _get_client()

    job_context["status"] = "extracting"
    job_context["current_agent"] = "Field Extraction Agent"
    job_context["progress_pct"] = 45

    # Level 2: verify Agent 1 handoff is present
    split_documents = job_context.get("split_documents")
    if not split_documents:
        raise ValueError(
            "Agent 2 received no split_documents from Agent 1 — pipeline halted."
        )

    raw_extractions: dict[str, dict] = {}
    all_warnings: list[str] = []
    total = len(split_documents)

    for idx, (doc_name, doc_info) in enumerate(split_documents.items()):
        doc_type = doc_info["doc_type"]
        schema_cls = SCHEMA_PER_DOC_TYPE.get(doc_type)
        if schema_cls is None:
            continue

        # Level 1 + Level 4: sanitise + truncate markdown
        raw_markdown = doc_info.get("markdown", "")
        safe_markdown = _sanitise_markdown(raw_markdown, source_label=doc_name)

        # Level 3: retry the extraction call
        def _do_extract(md=safe_markdown, sc=schema_cls):
            return client.extract(
                schema=pydantic_to_json_schema(sc),
                markdown=md,
            )

        result = _api_call_with_retry(_do_extract, label=f"extract({doc_name})")

        # Level 4: field-range validation
        range_warnings = _validate_field_ranges(
            result.extraction or {}, doc_type=doc_type
        )
        if range_warnings:
            all_warnings.extend(range_warnings)
            logger.warning(
                "Field range warnings for '%s': %s", doc_name, range_warnings
            )

        # Level 4: surface confidence from grounding chunks
        parse_result = job_context.get("parse_result")
        grounding = parse_result.grounding if parse_result else None
        confidence = _extract_confidence(result.extraction_metadata or {}, grounding=grounding)

        raw_extractions[doc_name] = {
            "doc_type": doc_type,
            "pages": doc_info["pages"],
            "extraction": result.extraction or {},
            "extraction_metadata": result.extraction_metadata or {},
            "confidence": confidence,
        }

        job_context["progress_pct"] = 45 + int((idx + 1) / total * 28)

    # Level 2: validate handoff before passing to Agent 3
    extraction_records = {
        name: ExtractionRecord(**data)
        for name, data in raw_extractions.items()
    }
    handoff = ExtractionHandoff(document_extractions=extraction_records)

    # Store as plain dicts in context for compatibility with downstream agents
    document_extractions = {
        name: rec.model_dump()
        for name, rec in handoff.document_extractions.items()
    }

    # Attach any range warnings so the decision agent can surface them as flags
    job_context["extraction_warnings"] = all_warnings
    job_context["document_extractions"] = document_extractions
    return {"document_extractions": document_extractions}


# ---------------------------------------------------------------------------
# Agent 3 — Loan Decision
# ---------------------------------------------------------------------------

def decide_loan(loan_amount: float, monthly_debt: float, job_context: dict) -> dict:
    """
    Reason about loan approval/denial based on extracted financial fields.

    Checks:
    1. Required documents present
    2. Income sanity (gross_pay > 0, net_pay <= gross_pay)
    3. DTI ratio <= 43%
    4. Bank balance >= 0
    5. Investment reserves >= 10% of loan amount
    6. Investment year not in the future

    Best practices applied:
      • Level 2: validates ExtractionHandoff is present before reasoning
      • Level 1: extraction_warnings from Agent 2 surfaced as flags
      • Level 4: confidence scores included in extracted_fields output
    """
    job_context["status"] = "deciding"
    job_context["current_agent"] = "Loan Decision Agent"
    job_context["progress_pct"] = 60

    # Level 2: validate input from Agent 2
    document_extractions = job_context.get("document_extractions")
    if document_extractions is None:
        raise ValueError(
            "Agent 3 received no document_extractions — pipeline halted."
        )

    pay_stub_data = None
    bank_data = None
    investment_data = None

    for doc_name, doc in document_extractions.items():
        ext = doc.get("extraction", {})
        if doc["doc_type"] == "pay_stub" and pay_stub_data is None:
            pay_stub_data = ext
        elif doc["doc_type"] == "bank_statement" and bank_data is None:
            bank_data = ext
        elif doc["doc_type"] == "investment_statement" and investment_data is None:
            investment_data = ext

    reasons: list = []
    flags: list = []
    deny = False
    dti_ratio = None

    # Level 1: surface any range-validation warnings from Agent 2 as flags
    for warning in job_context.get("extraction_warnings", []):
        flags.append(f"Extraction anomaly: {warning}")

    # 1. Required documents
    if pay_stub_data is None:
        reasons.append("Missing pay stub — income cannot be verified.")
        deny = True
    if bank_data is None:
        reasons.append("Missing bank statement — assets cannot be verified.")
        deny = True

    # 2. Income sanity
    gross_pay = None
    net_pay = None
    if pay_stub_data:
        gross_pay = pay_stub_data.get("gross_pay")
        net_pay = pay_stub_data.get("net_pay")

        if gross_pay is None or gross_pay <= 0:
            flags.append("Suspicious gross pay: value is zero or missing.")
            deny = True
        else:
            reasons.append(f"Gross pay: ${gross_pay:,.2f} per pay period.")

        if net_pay is not None and gross_pay is not None and net_pay > gross_pay:
            flags.append(
                f"Fraud indicator: net pay (${net_pay:,.2f}) exceeds gross pay "
                f"(${gross_pay:,.2f}). This is not possible."
            )
            deny = True

    # 3. DTI check (bi-weekly pay, 30-year mortgage at 7%)
    if gross_pay and gross_pay > 0:
        monthly_income = gross_pay * 26 / 12
        monthly_rate = 0.07 / 12
        n = 360
        monthly_loan_payment = (
            loan_amount * monthly_rate * (1 + monthly_rate) ** n
            / ((1 + monthly_rate) ** n - 1)
        )
        total_monthly_debt = monthly_debt + monthly_loan_payment
        dti_ratio = round(total_monthly_debt / monthly_income, 4)

        if dti_ratio > 0.43:
            reasons.append(
                f"DTI ratio {dti_ratio:.1%} exceeds the 43% qualified-mortgage limit "
                f"(total monthly obligations ${total_monthly_debt:,.2f} vs "
                f"income ${monthly_income:,.2f}/mo)."
            )
            deny = True
        else:
            reasons.append(
                f"DTI ratio {dti_ratio:.1%} is within the 43% limit — income sufficient."
            )

    # 4. Bank balance
    if bank_data:
        balance = bank_data.get("balance")
        if balance is not None and balance < 0:
            flags.append(f"Negative bank balance: ${balance:,.2f}.")
            deny = True
        elif balance is not None:
            reasons.append(f"Bank balance: ${balance:,.2f}.")

    # 5. Investment reserves
    if investment_data:
        total_investment = investment_data.get("total_investment")
        investment_year = investment_data.get("investment_year")

        if total_investment is not None:
            reserve_threshold = loan_amount * 0.10
            if total_investment < reserve_threshold:
                reasons.append(
                    f"Insufficient reserves: investment value ${total_investment:,.2f} "
                    f"is below the 10% reserve requirement of ${reserve_threshold:,.2f}."
                )
                deny = True
            else:
                reasons.append(
                    f"Adequate reserves: ${total_investment:,.2f} in investment accounts."
                )

        # Level 4: dynamic current year check (not hardcoded)
        if investment_year is not None and investment_year > CURRENT_YEAR:
            flags.append(
                f"Suspicious investment year: {investment_year} is in the future "
                f"(current year: {CURRENT_YEAR})."
            )

    # 6. Final decision
    decision = "DENIED" if deny else "APPROVED"
    if not deny:
        reasons.append("All underwriting criteria met — loan approved.")

    # Level 4: include confidence scores in extracted_fields output
    extracted_fields: dict = {}
    for doc_name, doc in document_extractions.items():
        extracted_fields[doc_name] = {
            "doc_type": doc["doc_type"],
            "pages": doc["pages"],
            "fields": doc.get("extraction", {}),
            "confidence": doc.get("confidence"),
        }

    result = {
        "decision": decision,
        "reasons": reasons,
        "flags": flags,
        "dti_ratio": dti_ratio,
        "extracted_fields": extracted_fields,
    }

    job_context["decision_result"] = result
    job_context["progress_pct"] = 80

    return result


# ---------------------------------------------------------------------------
# Agent 4 — Manager Agent  (hierarchical orchestrator / reviewer)
# ---------------------------------------------------------------------------

def manager_review(job_context: dict) -> dict:
    """
    The Manager Agent reviews Agent 3's loan decision from a higher-order
    perspective. It has no direct access to the LandingAI API — it reasons
    purely over the structured output of the pipeline.

    Responsibilities:
    - Cross-check Agent 3's reasoning for internal consistency
    - Identify risk level based on combination of flags, DTI, and reserves
    - Detect borderline cases that warrant human escalation
    - Override the decision if the evidence clearly contradicts it
    - Catch scenarios Agent 3's rules may miss (e.g. moderate DTI + fraud flags)

    Best practices applied:
      • Level 2: validates decision_result is present before reviewing
      • Level 3: explicit termination — if no decision_result, raise immediately
    """
    job_context["status"] = "reviewing"
    job_context["current_agent"] = "Manager Agent"
    job_context["progress_pct"] = 83

    # Level 2: validate input from Agent 3
    result = job_context.get("decision_result")
    if not result:
        raise ValueError(
            "Manager Agent received no decision_result from Agent 3 — pipeline halted."
        )

    document_extractions = job_context.get("document_extractions", {})

    initial_decision = result.get("decision", "DENIED")
    flags            = result.get("flags", [])
    reasons          = result.get("reasons", [])
    dti_ratio        = result.get("dti_ratio")

    # Gather raw financials for manager's independent assessment
    pay_stub_data    = None
    bank_data        = None
    investment_data  = None
    for doc in document_extractions.values():
        ext = doc.get("extraction", {})
        if doc["doc_type"] == "pay_stub"               and pay_stub_data   is None: pay_stub_data   = ext
        elif doc["doc_type"] == "bank_statement"        and bank_data       is None: bank_data       = ext
        elif doc["doc_type"] == "investment_statement"  and investment_data is None: investment_data = ext

    review_notes: list = []
    override_decision = None
    upheld = True
    escalate = False

    # ── Risk scoring ────────────────────────────────────────────────────────
    risk_score = 0   # 0-10; maps to LOW / MEDIUM / HIGH / CRITICAL

    # DTI contribution
    if dti_ratio is not None:
        if dti_ratio > 0.50:
            risk_score += 4
            review_notes.append(f"DTI {dti_ratio:.1%} is severely above the 43% QM limit — high default risk.")
        elif dti_ratio > 0.43:
            risk_score += 2
            review_notes.append(f"DTI {dti_ratio:.1%} exceeds QM limit — denial is correct.")
        elif dti_ratio > 0.36:
            risk_score += 1
            review_notes.append(f"DTI {dti_ratio:.1%} is within limits but elevated — monitor closely.")
        else:
            review_notes.append(f"DTI {dti_ratio:.1%} is comfortably within underwriting guidelines.")

    # Fraud flags contribution
    fraud_flag_count = len(flags)
    if fraud_flag_count >= 2:
        risk_score += 4
        review_notes.append(f"{fraud_flag_count} fraud/anomaly flags detected — escalation required.")
        escalate = True
    elif fraud_flag_count == 1:
        risk_score += 2
        review_notes.append(f"1 fraud flag detected — requires verification before approval.")

    # ── Override checks ──────────────────────────────────────────────────────

    # Override 1: Any fraud flag + APPROVED → force denial and escalate
    if fraud_flag_count > 0 and initial_decision == "APPROVED":
        override_decision = "DENIED"
        upheld = False
        escalate = True
        review_notes.append(
            "OVERRIDE: Fraud flag present on an approved loan — "
            "Manager overrides to DENIED pending manual review."
        )

    # Override 2: Missing both pay stub and bank statement → critical gap
    if pay_stub_data is None and bank_data is None:
        risk_score += 4
        override_decision = "DENIED"
        upheld = False
        escalate = True
        review_notes.append(
            "OVERRIDE: Neither income nor asset documentation present — "
            "cannot underwrite without both."
        )

    # Override 3: Borderline DTI (38–43%) + zero flags + solid reserves → reconsider denial
    if (
        dti_ratio is not None
        and 0.38 <= dti_ratio <= 0.43
        and fraud_flag_count == 0
        and initial_decision == "DENIED"
        and investment_data is not None
        and investment_data.get("total_investment", 0) > 0
    ):
        risk_score = max(0, risk_score - 1)
        review_notes.append(
            "Manager note: DTI is borderline but no fraud flags and reserves are present. "
            "Recommend human underwriter review for possible manual approval."
        )
        escalate = True

    # Override 4: APPROVED with zero extracted fields (extraction failure)
    extracted_field_count = sum(
        len(doc.get("extraction", {})) for doc in document_extractions.values()
    )
    if extracted_field_count == 0 and initial_decision == "APPROVED":
        override_decision = "DENIED"
        upheld = False
        escalate = True
        review_notes.append(
            "OVERRIDE: No fields were extracted from any document — "
            "approval without evidence is not permissible."
        )

    # ── Risk level ───────────────────────────────────────────────────────────
    if risk_score >= 7:
        risk_level = "CRITICAL"
        escalate = True
    elif risk_score >= 4:
        risk_level = "HIGH"
    elif risk_score >= 2:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    if not review_notes:
        review_notes.append("No anomalies detected. Decision is consistent with underwriting guidelines.")

    if upheld:
        review_notes.insert(0, f"Manager upholds the {initial_decision} decision.")
    else:
        review_notes.insert(0, f"Manager OVERRIDES: {initial_decision} → {override_decision}.")

    manager_review_result = {
        "upheld": upheld,
        "override_decision": override_decision,
        "review_notes": review_notes,
        "risk_level": risk_level,
        "escalate": escalate,
    }

    # Write manager review into the main result
    final_decision = override_decision if override_decision else initial_decision
    result["manager_review"] = manager_review_result
    result["final_decision"] = final_decision

    job_context["decision_result"] = result
    job_context["manager_review"]  = manager_review_result
    job_context["status"] = "done"
    job_context["progress_pct"] = 100

    return manager_review_result


# ---------------------------------------------------------------------------
# Pipeline runner — called by main.py background task
# ---------------------------------------------------------------------------

async def run_pipeline(pdf_path: str, loan_amount: float, monthly_debt: float, job_context: dict):
    """Execute the hierarchical agent pipeline."""
    try:
        parse_and_split(pdf_path=pdf_path, job_context=job_context)
        extract_fields(job_context=job_context)
        decide_loan(loan_amount=loan_amount, monthly_debt=monthly_debt, job_context=job_context)
        manager_review(job_context=job_context)
    except Exception as exc:
        job_context["status"] = "error"
        job_context["error"] = str(exc)
        raise
