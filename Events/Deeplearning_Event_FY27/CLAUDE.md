# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A full-stack loan origination demo: a FastAPI backend running a 4-agent pipeline orchestrated by **Google ADK (Agent Development Kit)**, served alongside a vanilla JS/HTML/CSS frontend. The app parses mixed financial PDF packets page-by-page using LandingAI ADE, classifies and extracts structured fields, then applies underwriting rules via a Claude LlmAgent with a hierarchical Manager LlmAgent review.

## Setup

```bash
pip install landingai-ade fastapi uvicorn python-multipart python-dotenv pillow pymupdf aiofiles "anthropic>=0.40.0" google-adk
```

Create `.env` at the project root (alongside `backend/`):
```
VISION_AGENT_API_KEY=your_landingai_key
ANTHROPIC_API_KEY=your_anthropic_key
```

Both keys are required. `VISION_AGENT_API_KEY` drives Agents 1+2 (ADE parse/extract). `ANTHROPIC_API_KEY` drives Agents 3+4 (Claude LlmAgents) and the `/chat` endpoint.

## Running

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Frontend is served as static files from `http://localhost:8000`.

## Architecture

### ADK Pipeline (`backend/agents.py`)

Four agents are chained in an ADK `SequentialAgent` (`LoanOriginationPipeline`). Inter-agent state flows through the ADK session `state` dict via `EventActions(state_delta={...})` — not a mutable shared dict.

1. **`ParseSplitAgent`** (`BaseAgent`) — Calls `client.parse(split="page")`, classifies each page with the `DocType` schema, groups consecutive same-type pages into named logical documents via `group_pages_by_document_type()`. Yields `state_delta` events updating `split_documents` and `parse_result_grounding`.

2. **`FieldExtractionAgent`** (`BaseAgent`) — Reads `split_documents` from session state, looks up Pydantic schemas from `SCHEMA_PER_DOC_TYPE`, calls `client.extract()` per document, runs field-range validation. Yields `state_delta` updating `document_extractions` and `extraction_warnings`.

3. **`LoanDecisionAgent`** (`LlmAgent` — `AnthropicLlm("claude-haiku-4-5-20251001")`) — Instruction is a callable that reads `document_extractions`, `loan_amount`, and `monthly_debt` from session state and injects them into a structured prompt. Claude applies exactly the 6 defined underwriting rules and outputs a single JSON object. Result stored in `session.state["loan_decision_json"]` via `output_key=`. The prompt explicitly forbids inventing rules beyond the 6 listed; `flags` is restricted to Rule 2 and Rule 6 violations only.

4. **`ManagerReviewAgent`** (`LlmAgent` — `AnthropicLlm("claude-haiku-4-5-20251001")`) — Instruction reads `loan_decision_json` and `document_extractions` from state. Claude scores risk (0–10) based solely on DTI and flags already present in the decision, checks 4 override conditions, and outputs a single JSON object. Result stored in `session.state["manager_review_json"]`. The prompt forbids adding new flags or overriding based on criteria not in the underwriting rules.

Both `LlmAgent`s are wrapped in `_ProgressAgent` (a thin `BaseAgent`) that writes `status` / `current_agent` / `progress_pct` to session state before and after delegation.

`build_pipeline()` constructs and returns the `SequentialAgent`. `extract_pipeline_result()` parses the two JSON outputs from session state into the result dict expected by the frontend.

**`skip_ade` flag**: when `/analyze` reuses cached extractions, the session is seeded with `skip_ade=True`. `ParseSplitAgent` and `FieldExtractionAgent` detect this and yield an empty event immediately, letting the LlmAgents run against the pre-cached data.

All ADE API calls are wrapped in `_api_call_with_retry()` (3 attempts, exponential backoff starting at 1.5s). All markdown is sanitised for prompt injection and capped at 12,000 chars before extraction.

### Typed Handoffs (`backend/schemas.py`)

`ParseHandoff` and `ExtractionHandoff` (containing `ExtractionRecord` per document) validate inter-agent data on construction and raise `ValueError` to halt the pipeline on bad inputs. These are validated inside the `BaseAgent` implementations before writing to session state.

### API Layer (`backend/main.py`)

A singleton `Runner` (`_adk_runner`) wraps the `SequentialAgent` with an `InMemorySessionService`. Both are created at module import time.

Two async flows:
- **Upload flow**: `POST /upload` → creates an ADK session, calls `run_pipeline()` (runs all 4 agents) → `GET /upload-status/{doc_id}` polls `docs[doc_id]`
- **Analysis flow**: `POST /analyze` → creates an ADK session seeded with cached `document_extractions` + `skip_ade=True`, calls `_adk_runner.run_async()` (Agents 1+2 no-op, Agents 3+4 run) → `GET /status/{job_id}` → `GET /result/{job_id}`

ADK `state_delta` events are mirrored into `job_context` as they stream, so the existing polling endpoints keep working unchanged.

**Demo mode**: `GET /demo` skips the ADK pipeline entirely, loading `cache/document_extractions.json` and `cache/grounding_images.json`. Returns a `doc_id` that feeds directly into `/analyze`.

**Chat agent**: `POST /chat` calls `claude-haiku-4-5-20251001` directly via the `anthropic` SDK (not ADK) with a dynamically built system prompt grounded in the borrower's extracted financials.

### Frontend (`frontend/`)

Single-page app — no build step. `app.js` polls the status endpoints and drives the UI state machine. Scenario suggestions from the chat agent are parsed from ` ```scenario ``` ` code blocks and auto-fill the loan form.

### Utilities (`ade_utils.py`)

- `group_pages_by_document_type()` — core page-grouping logic used by `ParseSplitAgent`; handles both live ADE objects and cached dicts.
- Visualization and cache helpers used by the companion notebook.

## Demo Cache Regeneration

To regenerate `cache/document_extractions.json` and `cache/grounding_images.json`, run `Deeplearning_AI_Dev_Day_2026_Demo.ipynb` against `input_folder/loan_packet.pdf`. These are the only files required at runtime for demo mode.

## Extending

**Add a document type**: add schema to `schemas.py`, register in `SCHEMA_PER_DOC_TYPE`, add the literal to `DocType`, add field ranges to `FIELD_RANGES` in `agents.py`, update the underwriting rules in `_build_decision_instruction()`.

**Add an underwriting rule**: edit the `UNDERWRITING RULES` section of `_build_decision_instruction()` in `agents.py`. The LoanDecisionAgent (Claude) reads these rules from its system prompt.

**Swap the LLM**: change `AnthropicLlm(model="claude-haiku-4-5-20251001")` in the `LlmAgent` constructors in `agents.py`. Use `AnthropicLlm` for direct Anthropic API access (reads `ANTHROPIC_API_KEY`). Use `Claude` instead only if routing through Vertex AI (requires `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`).
