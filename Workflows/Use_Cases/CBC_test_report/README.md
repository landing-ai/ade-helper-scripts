# 🧬 Agentic Document Extraction (ADE) - CBC Lab Report Parser

This repository demonstrates how to extract structured information from CBC (Complete Blood Count) laboratory reports using [LandingAI's Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview) service via the `agentic_doc` Python package.

Try the Visual Playground at [Agentic Document Extraction Playground](https://va.landing.ai/demo/doc-extraction)

## 📌 What This Notebook Does

- Parses PDF files (`.pdf`) containing CBC lab reports using the LandingAI ADE API
- Defines a custom extraction schema using `pydantic` to model:
  - Patient information (name, age)
  - Sample and report details (referring doctor, sample type)
  - Laboratory information (lab name, pathologist)
  - Key blood parameters (hemoglobin values, RBC count)
- Processes CBC laboratory documents from a directory
- Saves extracted medical data as a structured CSV file

## 📦 Setup

### Prerequisites
Install dependencies:
```bash
pip install agentic-doc
```

### API Key
1. Get your API key from the [Visual Playground](https://va.landing.ai/settings/api-key)
2. Store it securely:
   - Recommended: create a `.env` file in the same directory:
     ```
     VISION_AGENT_API_KEY=your_api_key_here
     ```

## 📁 Directory Structure

The notebook uses three directories:
- `input_folder`: contains your CBC lab report files  
- `results_folder`: where the complete JSON response and the ultimate structured `.csv` outputs are saved 
- `groundings_folder`: where .png files for individual chunks are saved 

## 🧩 Schema

The schema is defined using Pydantic with fields like:
```python
class CBCLabReport(BaseModel):
    patient_name: str
    patient_age: str
    referring_doctor: str
    sample_type: str
    lab_name: str
    pathologist_name: str
    hemoglobin_value: float
    hemoglobin_status: Optional[str]
    rbc_count_value: float
    rbc_count_unit: str
```

## 📤 Output

After processing, a CSV file (`cbc_output.csv`) is saved in the `results_folder` directory.  
Each row in the CSV represents a structured extraction from a CBC lab report, including fields like patient information, laboratory details, and key blood test values.

Note: We have used a single CBC document here, this will create a DataFrame with only one row.

## 🧠 Additional Resources

- [LandingAI Agentic Document Extraction Documentation](https://docs.landing.ai/ade/ade-overview)  
- [agentic-doc Python Package on GitHub](https://github.com/landing-ai/agentic-doc)  
- [API Key Configuration Guide](https://docs.landing.ai/ade/agentic-api-key)

