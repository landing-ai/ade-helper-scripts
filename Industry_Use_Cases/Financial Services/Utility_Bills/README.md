# Fast, Accurate Parsing of Utility Bills with LandingAI

This folder contains assets and scripts demonstrating **Agentic Document Extraction (ADE)** on **Utility Bills** using the `landingai-ade` Python library. Utility bills are a common proof-of-address document in KYC and onboarding workflows.

Use this workflow to:

- Process PDFs or images of utility bills from many providers.
- Define custom fields to extract using a JSON schema.
- Run Agentic Document Extraction on a batch of utility bills and save the results.
- Save the extracted results with field-level metadata and chunk references.

To learn more visit the [LandingAI Documentation](https://docs.landing.ai/ade/ade-overview).


## 📁 Contents

- **parse_extract_utility_bills.ipynb**
  The main notebook that demonstrates the two-step Parse → Extract workflow using `landingai-ade`. Processes all utility bills in the input folder and saves organized outputs.

- **input_folder/**
  Place raw utility bill documents here (PDF, PNG, JPG, JPEG). 9 examples are included: 3 JPG and 6 PDF from different electric and gas utilities.

- **results_folder/**
  Processed results are written here after extraction:
  - `{filename}_parse.json` - Full parse response with markdown, chunks, and grounding
  - `{filename}.md` - Extracted text content
  - `{filename}_extract.json` - Structured extraction with field metadata
  - `utility_output.csv` - Summary CSV with all extracted fields and chunk references

- **utility_bill.json**
  JSON schema defining the expected fields to extract (e.g., provider info, account details, billing summary, electric/gas charges).

- **images/**
  Supporting images for documentation and visualization.

---

## 🚀 Prerequisites

1. Install the `landingai-ade` library and dependencies:

   ```bash
   pip install landingai-ade python-dotenv pandas
   ```

2. Set your LandingAI Vision Agent API key in a `.env` file:

   ```bash
   # Create .env file in this directory
   VISION_AGENT_API_KEY=your_api_key_here
   ```

   Get your API key from the [Visual Playground](https://va.landing.ai/settings/api-key).

   See [API Key Configuration Guide](https://docs.landing.ai/ade/agentic-api-key) for other configuration options.

---

## 📝 How It Works

The notebook uses a **two-step process**:

### Step 1: Parse
Converts utility bill documents into structured markdown with chunk and grounding metadata:
- **Input**: PDF or image file
- **Output**: Markdown text, chunks with bounding boxes, and metadata

### Step 2: Extract
Applies the JSON schema to extract specific fields:
- **Input**: Markdown from Step 1 + JSON schema (`utility_bill.json`)
- **Output**: Structured data matching your schema with field-level metadata and chunk references

---

## 🎯 Running the Notebook

1. Place your utility bills in `input_folder/`
2. Ensure your API key is set in `.env`
3. Open and run `parse_extract_utility_bills.ipynb`

The notebook will:
- Parse all documents in the input folder
- Extract structured data using the utility bill schema
- Save organized outputs to `results_folder/`
- Create a summary CSV with all extractions

---

## 📊 Output Structure

For each input file (e.g., `electric1.pdf`), the notebook generates:

1. **Parse outputs:**
   - `electric1_parse.json` - Full response with chunks and grounding coordinates
   - `electric1.md` - Extracted text only

2. **Extract outputs:**
   - `electric1_extract.json` - Structured data with field metadata and chunk references

3. **Summary:**
   - `utility_output.csv` - All extractions in a single CSV file with chunk references

---

## 🔧 Customizing the Schema

Edit `utility_bill.json` to:
- Add new fields to extract
- Modify field descriptions for better accuracy
- Change required vs. optional fields
- Adjust data types

The schema uses JSON Schema format. See [Extract Documentation](https://docs.landing.ai/ade/ade-python#extraction-with-json-schema-file) for details.

---

## 📚 Additional Resources

- [LandingAI ADE Documentation](https://docs.landing.ai/ade/ade-overview)
- [landingai-ade Python Library](https://github.com/landing-ai/ade-python)
- [Parse API Documentation](https://docs.landing.ai/ade/ade-python#parse%3A-getting-started)
- [Extract API Documentation](https://docs.landing.ai/ade/ade-python#extract%3A-getting-started)

---

## 📝 Notes

- This example uses the **landingai-ade** library (v1.4.0+), which replaces the legacy `agentic-doc` library
- The notebook includes helper functions to flatten nested extraction data and metadata for DataFrame compatibility
- Processing time depends on document size and complexity (typically 5-20 seconds per document)
- The schema supports nested structures (provider_info, account_info, billing_summary, charges)
