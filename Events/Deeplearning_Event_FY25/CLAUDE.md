# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a demonstration project for LandingAI's Agentic Document Extraction (ADE) service. The project showcases automated document classification and field extraction from mixed financial documents (pay stubs, bank statements, investment statements) using the `landingai-ade` Python package.

## Core Architecture

The workflow follows a two-phase extraction pattern:

1. **Document Categorization**: First classify each document into one of three types: `pay_stub`, `bank_statement`, or `investment_statement`
2. **Schema-Based Extraction**: Apply document-type-specific Pydantic schemas to extract structured data with visual grounding references

### Key Components

- **Parsing**: Documents are parsed using `client.parse()` to extract layout, content, and markdown representation
- **Classification**: Documents are classified using a Pydantic `DocType` schema with Literal types
- **Extraction**: Type-specific schemas (BankStatementSchema, InvestmentStatementSchema, PaymentStubSchema) extract structured fields
- **Visualization**: Bounding boxes show parsed chunks and extracted field locations

## Development Commands

### Environment Setup

```bash
pip install landingai-ade pillow pymupdf
# Optional for visualization examples:
pip install matplotlib pydantic_settings
```

### API Authentication

Set your LandingAI API key (obtain from https://va.landing.ai/settings/api-key):

```bash
export VISION_AGENT_API_KEY=your_api_key_here
```

### Running the Notebooks

Primary workflow notebook:
```bash
jupyter notebook ade_classify_extract_visualize.ipynb
```

Additional examples (various usage patterns):
```bash
jupyter notebook ade_examples.ipynb
```

Or use Jupyter Lab, VS Code with Jupyter extension, or execute cells programmatically.

## Directory Structure

- `input_folder/`: Contains sample financial documents (PDFs, images) for processing
- `results/`: Stores parsed documents with bounding boxes showing all detected chunks
- `results_extracted/`: Stores visualizations highlighting only extracted field locations

## Schema Design Pattern

When adding new document types:

1. Define a Pydantic model with descriptive `Field()` definitions
2. Add the schema to `schema_per_doc_type` dictionary
3. Update the `DocType` Literal to include the new document type
4. Use `pydantic_to_json_schema()` to convert schemas for API calls

## Extraction Metadata

All extraction results include `extraction_metadata` with:
- `value`: The extracted data value
- `references`: List of chunk IDs showing where the value was found in the document

Use `parse_result.grounding[chunk_id]` to get bounding box coordinates and page numbers for visual grounding.

## API Models and Patterns

- Use `model="dpt-2-latest"` for parsing operations
- Parse splits can be `"page"`, `"section"`, or custom chunking strategies
- ExtractResponse contains both `extraction` (data) and `extraction_metadata` (provenance)

## Working with Merged Documents

The `ade_classify_extract_visualize.ipynb` notebook demonstrates a specialized workflow for processing merged PDFs containing multiple document types:

1. Parse the merged document with `split="page"`
2. Classify each page individually to determine document type boundaries
3. Group consecutive pages of the same type into logical documents
4. Apply document-type-specific schemas to each grouped section

This pattern is useful when processing bulk submissions (e.g., loan application packets) where multiple document types are combined into a single file.

## Common Usage Patterns

The `ade_examples.ipynb` notebook demonstrates:
- Parsing entire documents vs. per-page parsing
- Processing directories of files
- Using asynchronous parse jobs with `client.parse_jobs.create()` and `client.parse_jobs.get()`
- Extracting from individual chunks vs. full documents
- Visualization with color-coded bounding boxes by chunk type
- Saving results to JSON format
