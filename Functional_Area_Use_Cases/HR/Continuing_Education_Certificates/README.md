# 🧠 Agentic Document Extraction (ADE) - CME Certificate Parser

This example demonstrates how to extract structured information from CME (Continuing Medical Education) certificates using [LandingAI's Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview) service via the `landingai-ade` Python package.

Try the Visual Playground at [Agentic Document Extraction Playground](https://va.landing.ai/demo/doc-extraction)

## 📌 What This Notebook Does

- **Parses** PDF and image files (`.pdf`, `.png`, `.jpg`, `.jpeg`) using the LandingAI ADE API
- **Extracts** structured data using a custom `pydantic` schema:
  - Recipient name
  - Issuing organization
  - Activity title
  - Award date
  - Credit value (string and numeric)
  - AMA PRA Category 1 & 2 indicators
- **Processes** multiple documents from a directory
- **Saves** organized outputs:
  - Full parse responses (JSON)
  - Markdown-only outputs (TXT)
  - Extraction results (JSON)
  - Summary CSV file

## 📦 Setup

### Prerequisites

Install the required dependencies:

```bash
pip install landingai-ade pillow pandas python-dotenv
```

Or use the provided virtual environment:

```bash
# From the repository root
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install landingai-ade pillow pandas python-dotenv
```

### API Key

1. Get your API key from the [Visual Playground](https://va.landing.ai/settings/api-key)
2. Store it securely in a `.env` file in the same directory as the notebook:

   ```
   VISION_AGENT_API_KEY=your_api_key_here
   ```

See [API Key Configuration Guide](https://docs.landing.ai/ade/agentic-api-key) for other configuration options.

## 📁 Directory Structure

```
Continuing_Education_Certificates/
├── input_folder/              # Your CME certificate files (.pdf, .png, .jpg, .jpeg)
├── results_folder/            # Organized outputs (auto-created)
│   ├── parse/                 # Full parse response JSON files
│   ├── markdown/              # Markdown-only text files
│   ├── extract/               # Extraction result JSON files
│   └── cme_output.csv         # Summary CSV with all extractions
├── field_extraction_notebook_cme.ipynb  # Main notebook
├── README.md                  # This file
└── .env                       # Your API key (create this)
```

## 🚀 How It Works

The notebook uses a **two-step process**:

### Step 1: Parse
Converts documents into structured markdown with chunk and grounding metadata:
- **Input**: PDF or image file
- **Output**:
  - Full parse response (JSON) with chunks, grounding coordinates, and metadata
  - Markdown text (TXT) for easy reading

### Step 2: Extract
Applies a custom Pydantic schema to extract specific fields:
- **Input**: Markdown from Step 1 + Pydantic schema
- **Output**: Structured data matching your schema with field-level metadata

## 🧩 Extraction Schema

The schema is defined using Pydantic:

```python
from pydantic import BaseModel, Field
from datetime import date

class CME(BaseModel):
    recipient_name: str = Field(description="Full name of the individual who received the certificate...")
    issuing_org: str = Field(description="Full name of the organization issuing the certificate.")
    activity_title: str = Field(description="Title of the CME activity or material completed...")
    date_awarded: date = Field(description="Date when the certificate or credit was awarded.")
    credit_awarded: str = Field(description="Amount and type of CME credit awarded...")
    credit_numeric: float = Field(description="Amount of CME credit awarded.")
    ama_pra_cat1: bool = Field(description="True if the CME credits awarded qualify for AMA PRA Category 1.")
    ama_pra_cat2: bool = Field(description="True if the CME credits awarded qualify for AMA PRA Category 2.")
```

## 📤 Output Files

For each input file (e.g., `CME_Mendez_ex1.png`), the notebook generates:

1. **Parse outputs:**
   - `results_folder/parse/CME_Mendez_ex1.json` - Full response with chunks and grounding
   - `results_folder/markdown/CME_Mendez_ex1.md` - Extracted text only

2. **Extract outputs:**
   - `results_folder/extract/CME_Mendez_ex1.json` - Structured data with metadata

3. **Summary:**
   - `results_folder/cme_output.csv` - All extractions in a single CSV file

## 🎯 Running the Notebook

1. Place your CME certificates in `input_folder/`
2. Ensure your API key is set in `.env`
3. Select the Python kernel: "Python (ade-helper-scripts)" or your preferred kernel
4. Run all cells in sequence

The notebook will:
- Parse all documents in the input folder
- Extract structured data using the CME schema
- Save organized outputs
- Create a summary CSV file

## 🧠 Additional Resources

- [LandingAI ADE Documentation](https://docs.landing.ai/ade/ade-overview)
- [landingai-ade Python Library](https://github.com/landing-ai/ade-python)
- [Parse API Documentation](https://docs.landing.ai/ade/ade-python#parse%3A-getting-started)
- [Extract API Documentation](https://docs.landing.ai/ade/ade-python#extract%3A-getting-started)
- [API Key Configuration Guide](https://docs.landing.ai/ade/agentic-api-key)

