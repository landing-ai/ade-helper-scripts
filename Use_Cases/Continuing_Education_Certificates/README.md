

# 🧠 Agentic Document Extraction (ADE) - CME Certificate Parser

This repository demonstrates how to extract structured information from CME (Continuing Medical Education) certificates using [LandingAI's Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview) service via the `agentic_doc` Python package.

## 📌 What This Notebook Does

- Parses PDF and image files (`.pdf`, `.png`, `.jpg`, `.jpeg`) using the LandingAI ADE API
- Defines a custom extraction schema using `pydantic` to model:
  - Recipient name
  - Issuing organization
  - Activity title
  - Award date
  - Credit value
  - AMA PRA Category 1 & 2 indicators
- Processes multiple documents from a directory
- Saves extracted data as a structured CSV file

## 📦 Setup

### Prerequisites

Install dependencies:

```bash
pip install agentic-doc

### API Key

1. Get your API key from the [Visual Playground](https://va.landing.ai/settings/api-key)
2. Store it securely:
   - Recommended: create a `.env` file in the same directory:

     ```
     VISION_AGENT_API_KEY=your_api_key_here
     ```

## 📁 Directory Structure

The notebook uses three directories:

- `input_folder`: contains your CME certificate files  
- `results_folder`: where the complete JSON reponse and the ultimate structured `.csv` outputs are saved 
- `groundings_folder`: where .png files for individual chunks are saved 

## 🧩 Schema

The schema is defined using Pydantic with fields like:

```python
class CME(BaseModel):
    recipient_name: str
    issuing_org: str
    activity_title: str
    date_awarded: date
    credit_awarded: str
    credit_numeric: float
    ama_pra_cat1: bool
    ama_pra_cat2: bool

## 📤 Output

After processing, a CSV file (`cme_output.csv`) is saved in the `results_folder` directory.  
Each row in the CSV represents a structured extraction from a CME certificate, including fields like recipient name, issuing organization, date awarded, credit type, and credit amount.

## 🧠 Additional Resources

- [LandingAI Agentic Document Extraction Documentation](https://docs.landing.ai/ade/ade-overview)  
- [agentic-doc Python Package on GitHub](https://github.com/landing-ai/agentic-doc)  
- [API Key Configuration Guide](https://docs.landing.ai/ade/agentic-api-key)

## 🎥 Demo

A walkthrough video accompanies this notebook to show:

- How to test your schema in the Virtual Playground
- How to use Agentic Document Extrcation with and without field extraction
- How to batch process documents and inspect results

The video complements the step-by-step flow demonstrated in this notebook.

[![Watch the Demo](https://img.youtube.com/vi/PPIFgGpP4vw/hqdefault.jpg)](https://www.youtube.com/watch?v=PPIFgGpP4vw)