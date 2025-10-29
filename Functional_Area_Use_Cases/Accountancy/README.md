# Agentic Document Extraction for Tax Preparation

This example demonstrates how to extract structured financial information from mixed client documents using [LandingAI's Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview) service via the `landingai-ade` Python package.

Accountants and tax professionals handle diverse financial documents from clients—pay stubs, bank statements, investment statements, and more. LandingAI's **Agentic Document Extraction (ADE)** enables these professionals to automatically categorize and extract structured, traceable data from mixed document types—with no templates required.

Try the Visual Playground at [Agentic Document Extraction Playground](https://va.landing.ai/demo/doc-extraction)

---

## 📌 What This Example Does

- Automatically categorizes financial documents (pay stubs, bank statements, investment statements)
- Applies document-specific extraction schemas using `pydantic`
- Extracts key financial data:
  - **Pay Stubs**: employee name, pay period, gross pay, net pay
  - **Bank Statements**: bank name, account number, balance
  - **Investment Statements**: investment year, total investment, changes in value
- Provides visual grounding references for each extracted field
- Processes multiple client documents from a directory
- Outputs structured JSON data ready for tax software import

---

## Core Benefits of ADE in Tax Preparation Workflows

- **Automatically Categorize Mixed Document Types**
  Clients submit various financial documents in bulk. ADE intelligently categorizes each document and applies the appropriate extraction schema.

- **Extract Key Financial Data with Visual Grounding**
  By visually grounding each data point, ADE provides auditable, traceable extractions that show exactly where each value came from.

- **Accelerate Tax Season & Client Service**
  Fast and accurate extraction speeds up tax preparation, reduces manual data entry errors, and frees accountants for strategic tax planning.

- **Integrate Easily Into Tax & Accounting Software**
  Extracted data flows directly into tax preparation software, accounting systems, or analytics pipelines with minimal transformation.

---

## Key Use Cases in Tax Preparation

### 1. Multi-Client Tax Document Processing
- **Document Types:** Pay stubs, bank statements, investment statements
- **Benefits:** Auto-categorizes and extracts employee compensation (gross/net pay), account balances, investment values; eliminates manual data entry for tax returns.

### 2. Income & Expense Documentation
- **Document Types:** 1099 forms, W-2s, receipts, invoices
- **Benefits:** Extracts income sources, deductible expenses, and tax-reportable amounts for accurate tax filing and compliance.

### 3. Bank Reconciliation for Tax Reporting
- **Document Types:** Bank statements, transaction records
- **Benefits:** Extracts transaction details and balances for reconciling client accounts and supporting tax deductions.

### 4. Investment Portfolio Analysis
- **Document Types:** Brokerage statements, year-end summaries, capital gains reports
- **Benefits:** Captures investment values, gains/losses, and year-over-year changes for tax planning and reporting.

### 5. Audit Trail & Compliance Support
- **Document Types:** Source documents, client correspondence, prior year returns
- **Benefits:** Enables structured retrieval and visual traceability of financial records for tax audits and compliance reviews.

---

## 📦 Setup

### Prerequisites

- Python 3.10+
- Jupyter

Main libraries used:

```bash
pip install landingai-ade
pip install pillow
pip install pymupdf
```

### API Key

1. Get your API key from the [Visual Playground](https://va.landing.ai/settings/api-key)
2. Use environment variable:

    ```bash
    export VISION_AGENT_API_KEY=your_api_key_here
    ```

## 📁 Directory Structure

The notebook uses organized directories:

- `tax_preparation`: contains client financial document files (PDFs, images)
- `results`: where parsed documents with visual annotations are saved
- `results_extracted`: where extracted field visualizations are saved

## 📤 Output

After processing, the notebook produces:

- **Structured JSON data** with extracted fields for each document
- **Extraction metadata** with visual grounding references showing the exact location of each extracted value
- **Annotated images** showing all parsed document chunks with bounding boxes
- **Field-specific visualizations** highlighting only the regions where data was extracted

Each extraction includes `references` that map back to specific chunks in the parsed document, enabling quick verification and audit trail compliance.

## 🧠 Additional Resources

- [LandingAI Agentic Document Extraction Documentation](https://docs.landing.ai/ade/ade-overview)
- [landingai-ade Python Package](https://pypi.org/project/landingai-ade/)
- [API Key Configuration Guide](https://docs.landing.ai/ade/agentic-api-key)
