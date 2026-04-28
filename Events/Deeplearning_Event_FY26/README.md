# Agentic Document Extraction for Mixed Document Types

### Deep Learning AI Dev Day 2025 Demo

This example demonstrates how to extract structured information from mixed documents using [LandingAI's Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview) service via the `landingai-ade` Python package.

It uses personal financial documents as an example, but the **workflow applies equally to all document types**.

Imagine you are a bank and individual loan applicants send you diverse financial documents showing income and assets to support their loan application. Common documents include pay stubs, bank statements, and investment statements. LandingAI's **Agentic Document Extraction (ADE)** enables the bank to automatically categorize the document and then extract structured, traceable data from each document—with no templates required.

Try the Visual Playground at [Agentic Document Extraction Playground](https://va.landing.ai/demo/doc-extraction)

---

## 📌 What This Example Does

- Automatically categorizes all documents found in the `input_folder/`. In this case there are 3 options: pay stub, bank statements, investment statements.
- Parses the full document
- Applies document-specific extraction schemas using `pydantic`
- Extracts key financial data:
  - **Pay Stubs**: employee name, pay period, gross pay, net pay
  - **Bank Statements**: bank name, account number, balance
  - **Investment Statements**: investment year, total investment, changes in value
- Provides visual grounding references for each extracted field
- Processes multiple client documents from a directory
- Outputs structured JSON data ready for use in downstream processes

---

## Core Benefits of ADE in Workflows with Mixed Document Types

- **Automatically Categorize Mixed Document Types**
  Clients submit various financial documents in bulk. ADE intelligently categorizes each document and applies the appropriate extraction schema.

- **Extract Key Financial Data with Visual Grounding**
  By visually grounding each data point, ADE provides auditable, traceable extractions that show exactly where each value came from.

- **Accelerate Loan Decisions and Reduce Manual Effort**
  Fast and accurate extraction speeds up loan decisions, reduces manual data entry errors, and frees staff time.

- **Integrate Easily Into Data Pipelines**
  Extracted data flows directly into other software, databases, systems, or analytics pipelines with minimal transformation.


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

## 🚀 Running the Demo

Open and run the main demo notebook:

```bash
jupyter notebook Deeplearning_AI_Dev_Day_2025_Demo.ipynb
```

Or use Jupyter Lab or VS Code with the Jupyter extension.

## 📁 Directory Structure

The notebook uses organized directories:

- `input_folder/`: contains client financial document files (PDFs, images)
- `results/`: where parsed documents with visual annotations are saved
- `results_extracted/`: where extracted field visualizations are saved
- `cache/`: cached API responses to speed up re-runs during development
- `ade_utils.py`: utility functions for visualization and document processing

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
