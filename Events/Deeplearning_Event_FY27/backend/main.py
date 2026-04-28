"""
FastAPI backend for the Loan Origination Multi-Agent System.

Endpoints:
  POST /upload              — Upload PDF; runs parse+extract (Agents 1+2); returns doc_id
  GET  /upload-status/{id}  — Poll parse+extract progress
  GET  /demo                — Instantly load pre-cached loan_packet extractions (skips Agents 1+2)
  POST /analyze             — Run loan decision (Agent 3) against cached doc_id; returns job_id
  GET  /status/{job_id}     — Poll decision progress
  GET  /result/{job_id}     — Retrieve final decision
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from schemas import JobResult, JobStatus, LoanDecision

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI(title="Loan Origination API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session stores
# ---------------------------------------------------------------------------

# doc_id -> {status, progress_pct, current_agent, document_extractions, error}
docs: dict[str, dict] = {}

# job_id -> {status, progress_pct, current_agent, decision_result, error}
jobs: dict[str, dict] = {}

UPLOAD_DIR = Path("/tmp/loan_origination_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Path to the pre-cached loan_packet extractions from the notebook
DEMO_CACHE_PATH    = Path(__file__).parent.parent / "cache" / "document_extractions.json"
GROUNDING_IMG_PATH = Path(__file__).parent.parent / "cache" / "grounding_images.json"

# Lazy-load grounding images (large JSON, load once)
_grounding_images: dict | None = None

def _get_grounding_images() -> dict:
    global _grounding_images
    if _grounding_images is None and GROUNDING_IMG_PATH.exists():
        _grounding_images = json.loads(GROUNDING_IMG_PATH.read_text())
    return _grounding_images or {}


# ---------------------------------------------------------------------------
# Endpoint 1: Upload + Parse + Extract  (Agents 1 & 2)
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload_document(
    pdf_file: UploadFile = File(..., description="Loan packet PDF"),
):
    """Save PDF, run parse & extract pipeline, cache extracted fields as a doc_id."""
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    doc_id = str(uuid.uuid4())

    pdf_path = UPLOAD_DIR / f"{doc_id}.pdf"
    contents = await pdf_file.read()
    pdf_path.write_bytes(contents)

    docs[doc_id] = {
        "status": "queued",
        "current_agent": None,
        "progress_pct": 0,
        "error": None,
        "document_extractions": None,
    }

    asyncio.create_task(_run_upload_task(doc_id, str(pdf_path)))

    return {"doc_id": doc_id}


@app.get("/upload-status/{doc_id}")
async def get_upload_status(doc_id: str):
    """Poll parse+extract progress."""
    doc = docs.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {
        "doc_id": doc_id,
        "status": doc["status"],
        "current_agent": doc.get("current_agent"),
        "progress_pct": doc.get("progress_pct", 0),
        "error": doc.get("error"),
        "document_extractions": doc.get("document_extractions") if doc["status"] == "ready" else None,
    }


# ---------------------------------------------------------------------------
# Endpoint 1b: Demo mode — instantly load pre-cached loan_packet extractions
# ---------------------------------------------------------------------------

@app.get("/demo")
async def load_demo():
    """
    Skip Agents 1+2 entirely by loading the pre-cached extractions from the
    notebook's cache/document_extractions.json.  Returns a doc_id that can
    be used directly with POST /analyze.

    Also injects per-field confidence scores (ratio of grounding references
    found vs. expected) and a has_grounding flag per field.
    """
    if not DEMO_CACHE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Demo cache not found. Run the notebook first to generate cache/document_extractions.json."
        )

    raw = json.loads(DEMO_CACHE_PATH.read_text())
    grounding = _get_grounding_images()

    # Annotate each field with confidence + grounding availability
    for doc_name, doc in raw.items():
        meta = doc.get("extraction_metadata", {})
        field_info: dict[str, dict] = {}
        for field, field_meta in meta.items():
            has_grounding = (
                doc_name in grounding and field in grounding[doc_name]
            )
            # Use real confidence score if present in cache, otherwise heuristic.
            conf = field_meta.get("confidence")
            if conf is None:
                refs = field_meta.get("references", [])
                if len(refs) == 0:
                    conf = 0.50
                elif len(refs) == 1:
                    conf = 0.85
                else:
                    conf = 0.95
            field_info[field] = {
                "confidence": conf,
                "has_grounding": has_grounding,
            }
        doc["field_info"] = field_info

    doc_id = str(uuid.uuid4())
    docs[doc_id] = {
        "status": "ready",
        "current_agent": None,
        "progress_pct": 100,
        "error": None,
        "document_extractions": raw,
    }

    return {
        "doc_id": doc_id,
        "document_extractions": raw,
        "source": "demo_cache",
        "filename": "loan_packet.pdf (cached)",
    }


@app.get("/grounding/{doc_name}/{field}")
async def get_grounding_image(doc_name: str, field: str):
    """
    Return the pre-rendered grounding image (base64 PNG) for a specific
    doc_name + field from the demo cache.
    """
    grounding = _get_grounding_images()
    doc_data = grounding.get(doc_name)
    if doc_data is None:
        raise HTTPException(status_code=404, detail=f"No grounding data for document '{doc_name}'.")
    field_data = doc_data.get(field)
    if field_data is None:
        raise HTTPException(status_code=404, detail=f"No grounding data for field '{field}' in '{doc_name}'.")
    return {
        "doc_name": doc_name,
        "field": field,
        "page": field_data["page"],
        "img_b64": field_data["img_b64"],
        "box_pct": field_data["box_pct"],
    }


# ---------------------------------------------------------------------------
# Endpoint 2: Scenario Analysis  (Agent 3 only — uses cached doc_id)
# ---------------------------------------------------------------------------

@app.post("/analyze")
async def analyze(
    doc_id: str = Form(..., description="doc_id from a completed upload"),
    loan_amount: float = Form(..., description="Requested loan amount in dollars"),
    monthly_debt: float = Form(..., description="Existing monthly debt obligations in dollars"),
):
    """Run the loan decision agent against previously extracted document data."""
    doc = docs.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found. Upload a PDF first.")
    if doc["status"] != "ready":
        raise HTTPException(status_code=400, detail="Document extraction not complete yet.")
    if loan_amount <= 0:
        raise HTTPException(status_code=400, detail="loan_amount must be greater than zero.")
    if monthly_debt < 0:
        raise HTTPException(status_code=400, detail="monthly_debt cannot be negative.")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued",
        "current_agent": None,
        "progress_pct": 0,
        "error": None,
        "decision_result": None,
    }

    asyncio.create_task(_run_analysis_task(job_id, doc_id, loan_amount, monthly_debt))

    return {"job_id": job_id}


@app.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Poll loan decision progress."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        current_agent=job.get("current_agent"),
        progress_pct=job.get("progress_pct", 0),
        error=job.get("error"),
    )


@app.get("/result/{job_id}", response_model=JobResult)
async def get_result(job_id: str):
    """Return final decision when complete."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] not in ("done", "error"):
        raise HTTPException(status_code=202, detail="Job is still processing.")

    decision = None
    if job.get("decision_result"):
        dr = job["decision_result"]
        from schemas import ManagerReview
        mr_data = dr.get("manager_review")
        mr = ManagerReview(**mr_data) if mr_data else None
        decision = LoanDecision(
            decision=dr["decision"],
            reasons=dr["reasons"],
            flags=dr["flags"],
            dti_ratio=dr.get("dti_ratio"),
            extracted_fields=dr.get("extracted_fields", {}),
            manager_review=mr,
            final_decision=dr.get("final_decision", dr["decision"]),
        )

    return JobResult(job_id=job_id, status=job["status"], decision=decision)


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _run_upload_task(doc_id: str, pdf_path: str):
    """Run Agents 1+2 in a thread pool; cache extractions in docs[doc_id]."""
    doc_context = docs[doc_id]
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _sync_upload, doc_id, pdf_path, doc_context)
    except Exception as exc:
        doc_context["status"] = "error"
        doc_context["error"] = str(exc)
    finally:
        Path(pdf_path).unlink(missing_ok=True)


def _sync_upload(doc_id, pdf_path, doc_context):
    from agents import parse_and_split, extract_fields
    try:
        parse_and_split(pdf_path=pdf_path, job_context=doc_context)
        extract_fields(job_context=doc_context)
        doc_context["status"] = "ready"
        doc_context["progress_pct"] = 100
        doc_context["current_agent"] = None
    except Exception as exc:
        doc_context["status"] = "error"
        doc_context["error"] = str(exc)
        raise


async def _run_analysis_task(job_id: str, doc_id: str, loan_amount: float, monthly_debt: float):
    """Run Agent 3 using cached extractions from docs[doc_id]."""
    job_context = jobs[job_id]
    doc = docs[doc_id]

    # Give the decision agent the cached extractions
    job_context["document_extractions"] = doc["document_extractions"]

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None, _sync_analysis, job_id, loan_amount, monthly_debt, job_context
        )
    except Exception as exc:
        job_context["status"] = "error"
        job_context["error"] = str(exc)


def _sync_analysis(job_id, loan_amount, monthly_debt, job_context):
    from agents import decide_loan, manager_review
    try:
        decide_loan(loan_amount=loan_amount, monthly_debt=monthly_debt, job_context=job_context)
        manager_review(job_context=job_context)
    except Exception as exc:
        job_context["status"] = "error"
        job_context["error"] = str(exc)
        raise


# ---------------------------------------------------------------------------
# Chat Agent  — Claude-powered advisor aware of borrower financials
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str          # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    doc_id: Optional[str] = None          # used to pull latest extractions
    run_results: Optional[List[dict]] = []  # past analysis results for context


def _build_system_prompt(doc_id: Optional[str], run_results: List[dict]) -> str:
    """Build a system prompt grounded in the borrower's actual extracted data."""

    # Pull live extractions from docs store if available
    extractions = {}
    if doc_id and doc_id in docs:
        extractions = docs[doc_id].get("document_extractions") or {}

    # Parse key financials
    gross_pay = net_pay = balance = total_investment = None
    employee_name = pay_period = bank_name = investment_year = None

    for doc in extractions.values():
        ext = doc.get("extraction", {})
        dt  = doc.get("doc_type", "")
        if dt == "pay_stub":
            gross_pay      = ext.get("gross_pay")
            net_pay        = ext.get("net_pay")
            employee_name  = ext.get("employee_name")
            pay_period     = ext.get("pay_period")
        elif dt == "bank_statement":
            balance        = ext.get("balance")
            bank_name      = ext.get("bank_name")
        elif dt == "investment_statement":
            total_investment = ext.get("total_investment")
            investment_year  = ext.get("investment_year")

    # Derived income metrics
    monthly_income     = round(gross_pay * 26 / 12, 2)  if gross_pay else None
    monthly_rate       = 0.07 / 12
    n                  = 360
    pmt_per_dollar     = monthly_rate * (1 + monthly_rate)**n / ((1 + monthly_rate)**n - 1)
    reserve_max_loan   = round(total_investment / 0.10, 0) if total_investment else None

    def max_loan_at_dti(target_dti, existing_debt=0):
        if not monthly_income:
            return None
        mp = target_dti * monthly_income - existing_debt
        if mp <= 0:
            return None
        return round(mp / pmt_per_dollar, 0)

    # Scenario boundary table (0 existing debt)
    scenarios = {
        "LOW (DTI ≤ 30%)":    max_loan_at_dti(0.30),
        "MEDIUM (DTI ≤ 36%)": max_loan_at_dti(0.36),
        "QM limit (DTI = 43%)": max_loan_at_dti(0.43),
        "HIGH (DTI = 50%)":   max_loan_at_dti(0.50),
        "CRITICAL (DTI = 58%)": max_loan_at_dti(0.58),
    }

    # Format past runs summary
    runs_text = ""
    if run_results:
        lines = []
        for i, r in enumerate(run_results, 1):
            d = r.get("decision", {})
            if not d:
                continue
            fd   = d.get("final_decision") or d.get("decision", "?")
            dti  = d.get("dti_ratio")
            loan = r.get("loan_amount")
            debt = r.get("monthly_debt")
            mr   = d.get("manager_review", {}) or {}
            risk = mr.get("risk_level", "?")
            lines.append(
                f"  Run {i}: loan=${loan:,.0f}, debt=${debt:,.0f}/mo → "
                f"{fd}, DTI={dti:.1%}, risk={risk}"
                if isinstance(dti, float) else
                f"  Run {i}: loan=${loan:,.0f}, debt=${debt:,.0f}/mo → {fd}, risk={risk}"
            )
        runs_text = "\n".join(lines) if lines else "  (none yet)"
    else:
        runs_text = "  (none yet)"

    borrower_block = f"""
BORROWER PROFILE (extracted from loan packet):
  Name:              {employee_name or "unknown"}
  Pay period:        {pay_period or "unknown"}
  Gross pay:         ${gross_pay:,.2f} (bi-weekly) → ${monthly_income:,.2f}/mo
  Net pay:           ${net_pay:,.2f}
  Bank ({bank_name or "unknown"}): ${balance:,.2f}
  Investments ({investment_year}): ${total_investment:,.2f}
  Monthly income:    ${monthly_income:,.2f}
  Max loan (reserve constraint): ${reserve_max_loan:,.0f}

RISK BOUNDARY SCENARIOS (assuming $0 existing debt, 30-yr fixed @ 7%):
  LOW risk ceiling       (DTI = 30%): up to ${scenarios['LOW (DTI ≤ 30%)']:,.0f}   → APPROVED, LOW risk
  MEDIUM risk ceiling    (DTI = 36%): up to ${scenarios['MEDIUM (DTI ≤ 36%)']:,.0f}   → APPROVED, MEDIUM risk
  QM approval limit      (DTI = 43%): up to ${scenarios['QM limit (DTI = 43%)']:,.0f}   → APPROVED, borderline
  HIGH risk threshold    (DTI = 50%): up to ${scenarios['HIGH (DTI = 50%)']:,.0f}   → DENIED, HIGH risk
  CRITICAL threshold     (DTI = 58%): up to ${scenarios['CRITICAL (DTI = 58%)']:,.0f}   → DENIED, CRITICAL risk

PAST SCENARIO RUNS:
{runs_text}
""" if gross_pay else "  (No borrower data loaded — demo mode or upload not complete)"

    return f"""You are an AI loan advisor assistant embedded in a loan origination system built on LandingAI's Agentic Document Extraction.

Your role:
- Explain loan decisions and underwriting reasoning in plain English
- Suggest specific loan amount / monthly debt combinations to explore different risk outcomes
- Help users understand how DTI ratio, income, reserves and fraud flags affect approval
- Be concise, direct, and data-driven — always cite the actual numbers from the borrower's profile
- When you suggest a scenario, always include a JSON block so the UI can auto-fill the form

{borrower_block}

UNDERWRITING RULES (implemented in Agent 3):
  - DTI ≤ 43% (Qualified Mortgage limit) required for approval
  - Monthly income = gross_pay × 26 ÷ 12 (bi-weekly payroll assumption)
  - Mortgage payment estimated at 30-year fixed, 7% APR
  - Investment reserves must be ≥ 10% of loan amount
  - Net pay must not exceed gross pay (fraud indicator)
  - Bank balance must be ≥ 0

MANAGER AGENT RISK SCORING:
  - DTI 36–43%: +1 risk point (monitor closely)
  - DTI 43–50%: +2 risk points → DENIED
  - DTI > 50%:  +4 risk points → DENIED, high default risk
  - 1 fraud flag: +2 risk points
  - 2+ fraud flags: +4 risk points, auto-escalate
  Score ≥ 7 → CRITICAL · ≥ 4 → HIGH · ≥ 2 → MEDIUM · else LOW

SUGGESTING SCENARIOS:
When you recommend a scenario the user should run, include this exact JSON at the end of your message so the UI can auto-fill the form:
```scenario
{{"loan_amount": 50000, "monthly_debt": 0, "label": "MEDIUM risk ceiling"}}
```
Only include one scenario block per message. Round loan_amount to the nearest $500.
"""


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Chat with a Claude-powered loan advisor that knows the borrower's
    extracted financials and all past run results.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set in .env")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = _build_system_prompt(req.doc_id, req.run_results or [])

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
        )

        reply = response.content[0].text
        return {"reply": reply}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat error: {exc}")


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
