"""
Pydantic schemas for the Loan Origination Multi-Agent System.
Document schemas are verbatim from the existing notebook workflow.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional, Dict, Any, List


# ---------------------------------------------------------------------------
# Document Classification
# ---------------------------------------------------------------------------

class DocType(BaseModel):
    doc_type: Literal["pay_stub", "bank_statement", "investment_statement"]


# ---------------------------------------------------------------------------
# Document-Specific Extraction Schemas  (reused from notebook)
# ---------------------------------------------------------------------------

class BankStatementSchema(BaseModel):
    bank_name: str = Field(description="Name of the bank")
    account_number: str = Field(description="Account number")
    balance: float = Field(description="Current account balance")


class InvestmentStatementSchema(BaseModel):
    investment_year: int = Field(description="Year of the investment statement")
    total_investment: float = Field(description="Total investment value")
    changes_in_value: float = Field(description="Changes in investment value")


class PaymentStubSchema(BaseModel):
    employee_name: str = Field(description="Name of the employee")
    pay_period: str = Field(description="Pay period covered by this stub")
    gross_pay: float = Field(description="Gross pay before deductions")
    net_pay: float = Field(description="Net pay after deductions")


# Schema registry — maps doc_type string to Pydantic model
SCHEMA_PER_DOC_TYPE: Dict[str, type] = {
    "pay_stub": PaymentStubSchema,
    "bank_statement": BankStatementSchema,
    "investment_statement": InvestmentStatementSchema,
}


# ---------------------------------------------------------------------------
# Level 2: Typed Agent Handoff Models
# These replace raw dict passing between agents so each downstream agent
# validates its inputs on receipt rather than silently working with None.
# ---------------------------------------------------------------------------

class ExtractionRecord(BaseModel):
    """Single document's extraction result — passed from Agent 2 → Agent 3."""
    doc_type: Literal["pay_stub", "bank_statement", "investment_statement"]
    pages: List[int]
    extraction: Dict[str, Any]
    extraction_metadata: Dict[str, Any] = {}
    # Level 4: confidence score surfaced from extraction_metadata
    confidence: Optional[float] = None

    @field_validator("extraction")
    @classmethod
    def extraction_not_empty_warning(cls, v: dict) -> dict:
        # Allowed to be empty (extraction failure is handled downstream),
        # but we log a validation note so it's explicit.
        return v


class ParseHandoff(BaseModel):
    """Output of Agent 1 → input contract for Agent 2."""
    split_documents: Dict[str, Any]   # keyed by doc name, value has doc_type + pages + markdown

    @field_validator("split_documents")
    @classmethod
    def must_have_at_least_one(cls, v: dict) -> dict:
        if not v:
            raise ValueError("Agent 1 produced no split documents — cannot proceed to extraction.")
        return v


class ExtractionHandoff(BaseModel):
    """Output of Agent 2 → input contract for Agent 3."""
    document_extractions: Dict[str, ExtractionRecord]

    @model_validator(mode="after")
    def warn_if_all_empty(self) -> "ExtractionHandoff":
        non_empty = sum(
            1 for r in self.document_extractions.values() if r.extraction
        )
        if non_empty == 0:
            raise ValueError(
                "All document extractions returned empty — possible API failure or "
                "unrecognised document format. Halting pipeline."
            )
        return self


# ---------------------------------------------------------------------------
# API Models
# ---------------------------------------------------------------------------

class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "parsing", "extracting", "deciding", "reviewing", "done", "error"]
    current_agent: Optional[str] = None
    progress_pct: int = 0
    error: Optional[str] = None


class ManagerReview(BaseModel):
    """Output of the Manager Agent's review of the Loan Decision Agent's output."""
    upheld: bool                        # True = agrees with decision, False = overrides
    override_decision: Optional[Literal["APPROVED", "DENIED"]] = None
    review_notes: List[str]             # Manager's reasoning / observations
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    escalate: bool = False              # True = flag for human underwriter


class LoanDecision(BaseModel):
    decision: Literal["APPROVED", "DENIED"]
    reasons: List[str]
    flags: List[str]          # fraud / anomaly flags shown in red on the UI
    dti_ratio: Optional[float] = None
    extracted_fields: Dict[str, Any] = {}
    manager_review: Optional[ManagerReview] = None   # populated after manager agent runs
    final_decision: Optional[Literal["APPROVED", "DENIED"]] = None  # manager's final word


class JobResult(BaseModel):
    job_id: str
    status: str
    decision: Optional[LoanDecision] = None
