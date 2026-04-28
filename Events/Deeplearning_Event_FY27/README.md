# Agentic Loan Origination — Multi-Agent Document Analysis

A production-ready multi-agent loan origination system powered by [LandingAI Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview). Upload a mixed financial document packet, extract structured fields in one pass, then run unlimited loan scenarios — each reviewed by a hierarchical Manager Agent that can override the decision, score risk, and escalate to a human underwriter.

---

## Overview

Traditional loan origination requires staff to manually review and transcribe data from multiple document types. This system automates the entire pipeline:

1. A PDF containing multiple financial documents is parsed page-by-page
2. Each page is classified and grouped into logical documents
3. Document-specific schemas extract structured financial fields with visual grounding
4. A loan decision agent applies underwriting rules and flags anomalies
5. A manager agent reviews the decision, scores risk, and can override

Extracted fields are cached per session — change the loan amount or debt obligations and re-run the decision instantly, without re-uploading the PDF.

---

## Agent Architecture

```
                    Manager Agent  (hierarchical reviewer)
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
  Parse & Split      Field Extraction   Loan Decision
   Agent (1)          Agent (2)          Agent (3)
```

### Agent 1 — Parse & Split
Calls `client.parse()` with `split="page"` to process the PDF page-by-page. Each page's markdown is classified using the `DocType` schema (`pay_stub`, `bank_statement`, or `investment_statement`). Consecutive pages of the same type are grouped into named logical documents (e.g. `pay_stub_1`, `bank_statement_2`).

**Progress:** 10% → 38%

### Agent 2 — Field Extraction
Iterates over logical documents from Agent 1 and calls `client.extract()` with a document-specific Pydantic schema. Returns structured fields with `extraction_metadata` containing bounding-box references for every extracted value.

| Document Type | Extracted Fields |
|---|---|
| Pay Stub | employee_name, pay_period, gross_pay, net_pay |
| Bank Statement | bank_name, account_number, balance |
| Investment Statement | investment_year, total_investment, changes_in_value |

**Progress:** 45% → 73%

### Agent 3 — Loan Decision
Applies underwriting rules in order:

| Check | Condition | Outcome |
|---|---|---|
| Required documents | Pay stub or bank statement missing | DENY |
| Income sanity | `gross_pay ≤ 0` or null | DENY + flag |
| Fraud detection | `net_pay > gross_pay` | DENY + flag |
| DTI ratio | `(monthly_debt + est. mortgage payment) / monthly_income > 43%` | DENY |
| Negative balance | `balance < 0` | DENY + flag |
| Reserve check | `total_investment < loan_amount × 10%` | DENY |
| Future year anomaly | `investment_year > current_year` | Flag only |

Monthly loan payment is estimated using a 30-year fixed mortgage at 7% APR. Monthly income is `gross_pay × 26 / 12` (bi-weekly payroll).

**Progress:** 60% → 80%

### Manager Agent — Hierarchical Reviewer
Reviews Agent 3's output independently. Has no access to the LandingAI API — reasons purely over structured data.

**Risk scoring (0–10):**
- DTI > 50%: +4 pts
- DTI 43–50%: +2 pts
- DTI 36–43%: +1 pt
- 2+ fraud flags: +4 pts, auto-escalate
- 1 fraud flag: +2 pts

**Risk levels:** score ≥ 7 → CRITICAL · ≥ 4 → HIGH · ≥ 2 → MEDIUM · else LOW

**Override conditions:**
1. Any fraud flag on an APPROVED loan → force DENIED + escalate
2. Both pay stub and bank statement missing → force DENIED + escalate
3. Borderline DTI (38–43%) with no flags and positive reserves → recommend human review
4. APPROVED with zero extracted fields (extraction failure) → force DENIED + escalate

**Progress:** 83% → 100%

---

## Features

- **Decoupled extraction and analysis** — extract once, run N scenarios without re-uploading
- **Demo mode** — loads the sample `loan_packet.pdf` instantly from cache with no API call
- **Visual grounding** — hover over any extracted field value to see the exact region of the source document that was used, highlighted with a bounding box
- **Confidence scores** — per-field extraction confidence badge (green ≥ 90% / yellow ≥ 70% / red below)
- **Live progress** — pipeline stages update in real time via polling
- **Results history** — each scenario run is preserved below the input panel for comparison
- **Manager override display** — UI shows Agent 3's original decision with a strikethrough when the Manager overrides it

---

## Setup

### Prerequisites

- Python 3.10+
- [LandingAI API key](https://va.landing.ai/settings/api-key)

### Install dependencies

```bash
pip install landingai-ade fastapi uvicorn python-multipart python-dotenv pillow pymupdf aiofiles
```

### Configure your API key

Create a `.env` file at the project root:

```
VISION_AGENT_API_KEY=your_api_key_here
```

---

## Running the App

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

### Upload mode
1. Drag and drop any loan packet PDF into the drop zone (or click Browse)
2. Click **Extract Fields** — the pipeline runs Agents 1 and 2
3. When extraction completes, the extracted fields panel appears
4. Enter a loan amount and existing monthly debt, then click **Run Analysis**
5. The decision appears below with full reasoning and manager review
6. Change the inputs and run again — no re-upload needed

### Demo mode
Click **⚡ Demo — load loan_packet.pdf instantly** to skip extraction entirely and jump straight to the scenario panel using pre-cached results. Each extracted field shows a confidence badge and a **👁 source** button — click it to see the highlighted region of the original document.

---

## Project Structure

```
├── backend/
│   ├── main.py          # FastAPI app and all endpoints
│   ├── agents.py        # 4-agent pipeline with best practices
│   ├── schemas.py       # Pydantic models — extraction schemas and typed handoff contracts
│   └── requirements.txt
├── frontend/
│   ├── index.html       # Single-page app shell
│   ├── app.js           # Upload flow, demo mode, polling, grounding popup
│   ├── style.css        # LandingAI brand styling
│   └── Logo.png
├── cache/
│   ├── document_extractions.json   # Pre-extracted fields for demo mode
│   └── grounding_images.json       # Pre-rendered highlighted crops for hover popup
├── input_folder/
│   └── loan_packet.pdf             # Sample 30-page mixed financial document
├── ade_utils.py                    # Page-grouping utility (shared with notebook)
├── Deeplearning_AI_Dev_Day_2026_Demo.ipynb
└── LandingAI_Loan_Origination_Tech_Deck.pptx
```

---

## API Reference

### `POST /upload`
Upload a loan packet PDF. Runs Agents 1 and 2 in the background.

**Request:** `multipart/form-data`
- `pdf_file` — PDF file (required)

**Response:**
```json
{ "doc_id": "uuid" }
```

---

### `GET /upload-status/{doc_id}`
Poll parse and extraction progress.

**Response:**
```json
{
  "doc_id": "uuid",
  "status": "queued | parsing | extracting | ready | error",
  "current_agent": "Parse & Split Agent",
  "progress_pct": 45,
  "error": null,
  "document_extractions": null
}
```
`document_extractions` is populated only when `status == "ready"`.

---

### `GET /demo`
Load pre-cached extractions instantly. Returns the same shape as a completed upload, plus `field_info` with confidence and grounding availability per field.

**Response:**
```json
{
  "doc_id": "uuid",
  "filename": "loan_packet.pdf (cached)",
  "source": "demo_cache",
  "document_extractions": {
    "pay_stub_1": {
      "doc_type": "pay_stub",
      "pages": [0],
      "extraction": { "employee_name": "MICHAEL D BRYAN", "gross_pay": 452.43, ... },
      "field_info": {
        "gross_pay": { "confidence": 0.85, "has_grounding": true }
      }
    }
  }
}
```

---

### `POST /analyze`
Run Agents 3 and Manager against a previously extracted document.

**Request:** `multipart/form-data`
- `doc_id` — from a completed upload or demo (required)
- `loan_amount` — requested loan amount in dollars (required, > 0)
- `monthly_debt` — existing monthly debt obligations in dollars (required, ≥ 0)

**Response:**
```json
{ "job_id": "uuid" }
```

---

### `GET /status/{job_id}`
Poll loan decision progress.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "queued | deciding | reviewing | done | error",
  "current_agent": "Loan Decision Agent",
  "progress_pct": 80,
  "error": null
}
```

---

### `GET /result/{job_id}`
Retrieve the final decision. Only available when `status == "done"`.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "done",
  "decision": {
    "decision": "APPROVED | DENIED",
    "final_decision": "APPROVED | DENIED",
    "dti_ratio": 0.382,
    "reasons": ["DTI ratio 38.2% is within the 43% limit — income sufficient.", "..."],
    "flags": [],
    "extracted_fields": {
      "pay_stub_1": {
        "doc_type": "pay_stub",
        "pages": [0],
        "fields": { "gross_pay": 452.43, "net_pay": 291.90, "..." },
        "confidence": 0.85
      }
    },
    "manager_review": {
      "upheld": true,
      "override_decision": null,
      "risk_level": "LOW",
      "escalate": false,
      "review_notes": ["Manager upholds the APPROVED decision.", "DTI 38.2% is within limits but elevated — monitor closely."]
    }
  }
}
```

---

### `GET /grounding/{doc_name}/{field}`
Return a pre-rendered PNG (base64) of the highlighted document region for a specific extracted field. Only available in demo mode.

**Example:** `GET /grounding/pay_stub_1/gross_pay`

**Response:**
```json
{
  "doc_name": "pay_stub_1",
  "field": "gross_pay",
  "page": 0,
  "img_b64": "iVBORw0KGgo...",
  "box_pct": { "left": 0.298, "top": 0.312, "right": 0.435, "bottom": 0.326 }
}
```

---

## Multi-Agent Best Practices

The pipeline implements hardening at all four levels:

### Level 1 — Agent Level
- **Prompt injection guard** — `_sanitise_markdown()` strips injection patterns (e.g. "ignore all previous instructions", `<system>` tags) from PDF-extracted text before every `client.extract()` call
- **Context window cap** — markdown is truncated at 12,000 characters per document to prevent oversized API payloads
- **Field-range validation** — extracted numeric values are checked against plausible financial bounds (e.g. `gross_pay` 0–$500k, `investment_year` 1900–current year)
- **Dynamic year bound** — `datetime.now().year` replaces any hardcoded year for anomaly detection

### Level 2 — Agent-to-Agent Communication
- **Typed handoff models** — `ParseHandoff` and `ExtractionHandoff` are Pydantic models that validate inter-agent messages on construction; `ExtractionRecord` is a typed wrapper for each document's extraction result
- **Validation on receipt** — each agent asserts its expected inputs are present and raises a `ValueError` with a clear message if not, halting the pipeline cleanly
- **Empty-extraction guard** — `ExtractionHandoff` raises if all documents returned empty extractions, catching silent API failures before they reach the decision agent
- **Confidence passthrough** — `ExtractionRecord.confidence` carries an averaged score from `extraction_metadata` through to the final API response

### Level 3 — Orchestration
- **Retry with exponential backoff** — `_api_call_with_retry()` wraps every `client.parse()` and `client.extract()` call with up to 3 attempts and doubling delays (1.5 s → 3 s → 6 s)
- **Structured final error** — all retries exhausted raises a `RuntimeError` with attempt count and last exception chained
- **Explicit termination** — unrecoverable input errors raise immediately; the FastAPI background task catches them and sets `status: error` with the message
- **Structured logging** — `logging.warning()` on every retry attempt, redacted injection, and truncated markdown

### Level 4 — Context / Data Layer
- **Markdown length guard** — `MAX_MARKDOWN_CHARS = 12,000` enforced before each extraction call
- **Post-extraction range validation** — `FIELD_RANGES` dict maps each field to `(lo, hi)` bounds; out-of-range values are stored in `extraction_warnings` and surfaced as flags in Agent 3's output
- **Extraction confidence** — `_extract_confidence()` averages per-field confidence from `extraction_metadata` into a single score per document
- **Warning propagation** — Agent 2 range warnings flow through `job_context["extraction_warnings"]` → Agent 3 flags → Manager Agent risk score

---

## Extending the System

### Add a new document type
1. Define a Pydantic schema in `backend/schemas.py`
2. Add it to `SCHEMA_PER_DOC_TYPE`
3. Add the string literal to `DocType`
4. Add expected field ranges to `FIELD_RANGES` in `backend/agents.py`
5. Add underwriting rules for the new type in `decide_loan()`

### Add a new underwriting rule
Add a check in `decide_loan()` in `backend/agents.py`. The function appends to `reasons` (informational) or `flags` (fraud/anomaly) and sets `deny = True` to reject the loan.

### Re-generate demo cache
Run the notebook `Deeplearning_AI_Dev_Day_2026_Demo.ipynb` with your own PDF. The cache files in `cache/` are the only files needed at runtime for demo mode.

---

## Resources

- [LandingAI ADE Documentation](https://docs.landing.ai/ade/ade-overview)
- [landingai-ade PyPI package](https://pypi.org/project/landingai-ade/)
- [ADE Playground](https://va.landing.ai/demo/doc-extraction)
- [Get an API key](https://va.landing.ai/settings/api-key)
