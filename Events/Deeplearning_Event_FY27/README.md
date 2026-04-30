# Agentic Loan Origination — Multi-Agent Document Analysis

A production-ready multi-agent loan origination system powered by [LandingAI Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview) and **Google ADK (Agent Development Kit)**. Upload a mixed financial document packet, extract structured fields in one pass, then run unlimited loan scenarios — each decided by a Claude LlmAgent and reviewed by a hierarchical Manager LlmAgent that can override the decision, score risk, and escalate to a human underwriter.

---

## Overview

Traditional loan origination requires staff to manually review and transcribe data from multiple document types. This system automates the entire pipeline:

1. A PDF containing multiple financial documents is parsed page-by-page
2. Each page is classified and grouped into logical documents
3. Document-specific schemas extract structured financial fields with visual grounding
4. A Claude LlmAgent applies underwriting rules and flags anomalies
5. A Claude Manager LlmAgent reviews the decision, scores risk, and can override

Extracted fields are cached per session — change the loan amount or debt obligations and re-run the decision instantly, without re-uploading the PDF.

---

## Agent Architecture

The four agents are chained in an ADK `SequentialAgent`. Inter-agent data flows through the ADK session `state` dict via `EventActions(state_delta={...})`.

```
                    ManagerReviewAgent  (LlmAgent — Claude)
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
  ParseSplitAgent   FieldExtractionAgent  LoanDecisionAgent
  (BaseAgent—ADE)   (BaseAgent—ADE)       (LlmAgent—Claude)
```

### Agent 1 — ParseSplitAgent (`BaseAgent`)
Calls `client.parse()` with `split="page"` to process the PDF page-by-page. Each page's markdown is classified using the `DocType` schema (`pay_stub`, `bank_statement`, or `investment_statement`). Consecutive pages of the same type are grouped into named logical documents (e.g. `pay_stub_1`, `bank_statement_2`). Writes `split_documents` to ADK session state.

**Progress:** 10% → 38%

### Agent 2 — FieldExtractionAgent (`BaseAgent`)
Reads `split_documents` from session state, calls `client.extract()` with a document-specific Pydantic schema per document. Writes `document_extractions` to session state.

| Document Type | Extracted Fields |
|---|---|
| Pay Stub | employee_name, pay_period, gross_pay, net_pay |
| Bank Statement | bank_name, account_number, balance |
| Investment Statement | investment_year, total_investment, changes_in_value |

**Progress:** 45% → 73%

### Agent 3 — LoanDecisionAgent (`LlmAgent` — `AnthropicLlm`)
A Claude `LlmAgent` backed by `AnthropicLlm` (direct Anthropic API, not Vertex). Its instruction is a callable that reads `document_extractions`, `loan_amount`, and `monthly_debt` from ADK session state and builds a structured prompt. Claude applies exactly the 6 rules below and returns a single JSON object — the prompt explicitly forbids inventing additional rules or flags. Result stored in `session.state["loan_decision_json"]`.

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

**Progress:** 75% → 88%

### Agent 4 — ManagerReviewAgent (`LlmAgent` — `AnthropicLlm`)
A Claude `LlmAgent` backed by `AnthropicLlm`. Its instruction reads `loan_decision_json` and `document_extractions` from session state. Claude scores risk using only the DTI and flags already present in the decision (no new flags invented), checks 4 override conditions, and returns JSON stored in `session.state["manager_review_json"]`.

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

**Progress:** 88% → 100%

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
- [Anthropic API key](https://console.anthropic.com/settings/keys) — required for the chat agent (`/chat` endpoint)

### Install dependencies

```bash
pip install landingai-ade fastapi uvicorn python-multipart python-dotenv pillow pymupdf aiofiles "anthropic>=0.40.0" google-adk
```

### Configure your API keys

Create a `.env` file at the project root:

```
VISION_AGENT_API_KEY=your_landingai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

`ANTHROPIC_API_KEY` is required for Agents 3 & 4 (Claude LlmAgents) and the chat feature. `VISION_AGENT_API_KEY` is required for Agents 1 & 2 (LandingAI ADE).

---

## Running the App

```bash
cd backend && uvicorn main:app --reload --port 8000
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
│   ├── main.py          # FastAPI app — ADK Runner + all endpoints
│   ├── agents.py        # ADK SequentialAgent pipeline (4 agents)
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
└── LandingAI_Deeplearning.AI_Event_SF_FY27.pdf
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
- **ADK session state** — all inter-agent data flows through the ADK session `state` dict via `EventActions(state_delta={...})`; no mutable shared dicts
- **Typed handoff models** — `ParseHandoff` and `ExtractionHandoff` validate inter-agent messages on construction; `ExtractionRecord` is a typed wrapper per document
- **Validation on receipt** — each `BaseAgent` asserts its expected inputs are present in session state before proceeding
- **Empty-extraction guard** — `ExtractionHandoff` raises if all documents returned empty extractions, catching silent API failures before they reach the LlmAgents

### Level 3 — Orchestration
- **ADK SequentialAgent** — ordered execution of all four agents is guaranteed by the ADK framework, not manual function call order
- **Retry with exponential backoff** — `_api_call_with_retry()` wraps every `client.parse()` and `client.extract()` call with up to 3 attempts and doubling delays (1.5 s → 3 s → 6 s)
- **`skip_ade` short-circuit** — analysis-only sessions seed `skip_ade=True`; Agents 1+2 yield empty events so Agents 3+4 run over cached extractions without ADE calls

### Level 4 — Context / Data Layer
- **Markdown length guard** — `MAX_MARKDOWN_CHARS = 12,000` enforced before each ADE extraction call
- **Post-extraction range validation** — `FIELD_RANGES` maps each field to `(lo, hi)` bounds; out-of-range values flow through `extraction_warnings` in session state → injected into the LoanDecisionAgent prompt as anomaly context
- **Structured LLM output** — both LlmAgents output strict JSON; `extract_pipeline_result()` strips markdown fences and parses with fallback error handling

---

## Extending the System

### Add a new document type
1. Define a Pydantic schema in `backend/schemas.py`
2. Add it to `SCHEMA_PER_DOC_TYPE`
3. Add the string literal to `DocType`
4. Add expected field ranges to `FIELD_RANGES` in `backend/agents.py`
5. Update the `UNDERWRITING RULES` block in `_build_decision_instruction()` in `agents.py`

### Add a new underwriting rule
Edit the `UNDERWRITING RULES` section of `_build_decision_instruction()` in `backend/agents.py`. The `LoanDecisionAgent` (Claude) reads these rules from its system prompt.

### Swap the LLM
Change `Claude(model="claude-haiku-4-5-20251001")` in the `LlmAgent` constructors in `agents.py` to any model supported by ADK (`Claude`, `Gemini`, etc.).

### Re-generate demo cache
Run the notebook `Deeplearning_AI_Dev_Day_2026_Demo.ipynb` with your own PDF. The cache files in `cache/` are the only files needed at runtime for demo mode.

---

## Resources

- [LandingAI ADE Documentation](https://docs.landing.ai/ade/ade-overview)
- [landingai-ade PyPI package](https://pypi.org/project/landingai-ade/)
- [ADE Playground](https://va.landing.ai/demo/doc-extraction)
- [Get a LandingAI API key](https://va.landing.ai/settings/api-key)
- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [google-adk PyPI package](https://pypi.org/project/google-adk/)
