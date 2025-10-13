# ADE Parse and Extract with Python

This workflow demonstrates how to use the LandingAI Agentic Document Extraction (ADE) Python library to parse and extract structured information from invoices.

## Overview

This demo shows a complete end-to-end pipeline for:
- Parsing invoice documents (PDF, PNG, JPG, JPEG) into structured markdown and chunks
- Defining custom extraction schemas using Pydantic
- Extracting structured invoice fields using the ADE Extract API
- Processing documents in parallel with progress tracking
- Organizing results into normalized database-ready tables

## What's Included

### Invoices_Demo/

The main demo folder containing:

#### Notebooks
- **`invoices_demo_ade.ipynb`** - Main tutorial notebook demonstrating the complete ADE workflow

#### Python Modules
- **`invoice_schema.py`** - Pydantic schema defining invoice extraction structure (6 categories, 30+ fields)
- **`ade_utilities.py`** - Helper functions for ADE operations:
  - API key management (environment variables, .env files)
  - Parse and save utilities
  - Combined parse + extract workflows
- **`invoice_utilities.py`** - Invoice-specific utilities:
  - Create normalized summary tables from extraction results
  - Convert ADE output to pandas DataFrames

#### Sample Data
- **`input_folder/`** - 27 sample invoice PDFs for testing
- **`results_folder/`** - Output directory containing:
  - Individual parse results (JSON files: `parse_invoice_*.json`)
  - Individual extraction results (JSON files: `extract_invoice_*.json`)
  - Summary CSV tables ready for database insertion

## Key Features

### Two-Step Extraction Pipeline

**Step 1: Parse**
- Converts documents into structured markdown
- Extracts individual text/image chunks
- Provides bounding box coordinates (grounding)
- Returns document metadata (version, processing time, page count)

**Step 2: Extract**
- Applies custom Pydantic schema to parsed content
- Extracts specific structured fields
- Returns validated data matching your schema

### Invoice Extraction Schema

The schema (`InvoiceExtractionSchema`) captures:

1. **Invoice Information** - Date, number, order date, PO number, payment status
2. **Customer Information** - Name, billing address, email
3. **Supplier Information** - Company name, address, contact details, tax IDs
4. **Order Details** - Payment terms, shipping carrier, tracking number
5. **Financial Totals** - Currency, total due, subtotal, tax, shipping, fees
6. **Line Items** - Product details (SKU, description, quantity, pricing)

### Parallel Processing

Process multiple documents efficiently:
- ThreadPoolExecutor for concurrent API calls
- Real-time progress bars with tqdm
- Configurable worker count and rate limiting
- Robust error handling

### Normalized Output Tables

Results are organized into 4 database-ready DataFrames:

1. **Markdown Table** - Full document text per invoice
2. **Chunks Table** - Document regions with bounding box coordinates
3. **Invoice Main Table** - Flattened invoice-level fields (one row per invoice)
4. **Line Items Table** - Product/service details (multiple rows per invoice)

All tables share common keys (`RUN_ID`, `INVOICE_UUID`) for easy database insertion.

## Prerequisites

### Installation

```bash
pip install landing-ade
```

### API Key Setup

Obtain your API Key from: https://va.landing.ai/settings/api-key

Set your API key using one of these methods:

**Option 1: Environment Variable**
```bash
export VISION_AGENT_API_KEY="your-api-key-here"
```

**Option 2: .env File**
Create a `.env` file in your project directory:
```
VISION_AGENT_API_KEY=your-api-key-here
```

Then load it in your code:
```python
from dotenv import load_dotenv
load_dotenv()
```

See the [ADE API Key Documentation](https://docs.landing.ai/ade/agentic-api-key) for more options.

## Quick Start

### Single Document Processing

```python
from pathlib import Path
from landingai_ade import LandingAIADE
from ade_utilities import parse_extract_save
from invoice_schema import InvoiceExtractionSchema

# Initialize client
client = LandingAIADE()

# Parse and extract a single document
parse_result, extract_result = parse_extract_save(
    document_path="input_folder/invoice_1.pdf",
    client=client,
    schema_class=InvoiceExtractionSchema,
    output_dir="results_folder"
)

# Access the structured extraction
invoice_data = extract_result.extraction
print(f"Invoice Number: {invoice_data.invoice_info.invoice_number}")
print(f"Total Due: {invoice_data.totals_summary.total_due}")
```

### Batch Processing with Progress Tracking

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Configuration
input_dir = Path("input_folder")
output_dir = Path("results_folder")
max_workers = 10

# Get all supported files
file_paths = [p for p in input_dir.glob("*.*")
              if p.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")]

# Process in parallel
def process_file(path):
    return parse_extract_save(path, client, InvoiceExtractionSchema, output_dir)

results_summary = []
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(process_file, p) for p in file_paths]
    for future in tqdm(as_completed(futures), total=len(futures)):
        results_summary.append(future.result())

print(f"Processed {len(results_summary)} documents successfully")
```

### Creating Summary Tables

```python
from invoice_utilities import create_invoice_summary_tables

# Convert results to normalized DataFrames
invoice_markdown, invoice_chunks, invoice_main, invoice_items = \
    create_invoice_summary_tables(results_summary)

# Save to CSV for database insertion
invoice_markdown.to_csv("results_folder/invoice_markdown.csv", index=False)
invoice_chunks.to_csv("results_folder/invoice_chunks.csv", index=False)
invoice_main.to_csv("results_folder/invoice_main.csv", index=False)
invoice_items.to_csv("results_folder/invoice_items.csv", index=False)

# View results
print(f"Processed {len(invoice_main)} invoices")
print(f"Extracted {len(invoice_items)} line items")
print(invoice_main[['INVOICE_NUMBER', 'TOTAL_DUE', 'SUPPLIER_NAME']].head())
```

## Usage Guide

### Running the Notebook

1. Open `Invoices_Demo/invoices_demo_ade.ipynb`
2. Set your `VISION_AGENT_API_KEY` in a `.env` file
3. Run all cells to see the complete workflow
4. Check the `results_folder/` for output files

### Customizing the Schema

To extract different fields, modify `invoice_schema.py`:

```python
from pydantic import BaseModel, Field

class MyCustomSchema(BaseModel):
    field_name: str = Field(..., description="Clear description for AI extraction")
    optional_field: Optional[float] = Field(None, description="Optional numeric field")
```

Note: ADE supports **one level of nested schemas**. You can have a top-level schema with nested models, but not deeper nesting.

### Adjusting Parallel Processing

In the notebook, tune these parameters:

```python
max_workers = 10  # Number of concurrent threads
pause_between_requests = 0.2  # Seconds between requests (rate limiting)
```

## Output Files

### Individual Results
- `parse_invoice_*.json` - Raw parse output with markdown, chunks, grounding
- `extract_invoice_*.json` - Structured extraction matching your schema

### Summary Tables
- `invoice_markdown.csv` - Full document text
- `invoice_chunks.csv` - Text regions with bounding boxes
- `invoice_main.csv` - Flattened invoice fields (1 row per invoice)
- `invoice_items.csv` - Line items (N rows per invoice)

## Supported Formats

- PDF (`.pdf`)
- PNG (`.png`)
- JPG/JPEG (`.jpg`, `.jpeg`)

More formats coming soon.

## Use Cases

This workflow is ideal for:
- Invoice processing and accounts payable automation
- Document digitization projects
- Data extraction for financial reporting
- Bulk document processing with structured output
- Building document understanding pipelines

## Additional Resources

- [LandingAI ADE Documentation](https://docs.landing.ai/ade/ade-overview)
- [ADE Extract API Reference](https://docs.landing.ai/ade/ade-extract)
- [LandingAI Visual Playground](https://va.landing.ai/)

## Notes

- Parse results can be reused for multiple extractions with different schemas
- Inspection of raw parsed content helps troubleshoot extraction issues
- All DataFrames include `RUN_ID` for batch tracking and `INVOICE_UUID` for document linking
- The `landingai-ade` library version used in this demo: 0.17.1

## Support

For issues or questions about the ADE library, refer to the [LandingAI Documentation](https://docs.landing.ai/).
