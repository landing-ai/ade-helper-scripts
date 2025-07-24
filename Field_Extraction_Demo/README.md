# 🧠 Agentic Document Extraction with LandingAI

This Jupyter Notebook demonstrates how to:
- Use LandingAI’s Agentic Document Extraction (ADE) API to parse and extract data from PDFs and images.
- Define a custom Pydantic schema (`Product`) for structured field extraction.
- Convert extraction results into a tabular format and save as CSV.

## 📦 Prerequisites

- Python 3.8+
- Virtual environment (recommended)
- ADE API key

## 🚀 Installation

See Quickstart at https://docs.landing.ai/ade/ade-quickstart

## 🔑 API Key Setup
Create a `.env` file in the project root:
VISION_AGENT_API_KEY=your_api_key_here

## 🗂️ Folder Structure

    .
    ├── field_extraction_notebook.ipynb   # Main notebook
    ├── input_folder/                     # PDF, PNG, JPG, JPEG files to process
    ├── results_folder/                   # Markdown & JSON outputs
    ├── groundings_folder/                # Extraction grounding visuals
    └── .env                              # API key (not committed)


## 📝 Notebook Workflow

1. **Setup & Imports**  
   Load standard libraries (`os`, `json`, `Path`), the ADE parser (`agentic_doc.parse`), Pydantic (`BaseModel`, `Field`), and Pandas.

2. **Define Input/Output Directories**  
   Configure and create `input_folder`, `results_folder`, and `groundings_folder`.

3. **Collect Document File Paths**  
   Scan `input_folder` for supported file types (`.pdf`, `.png`, `.jpg`, `.jpeg`).

4. **Run ADE (Raw Extraction)**  
   Call `parse()` to generate markdown summaries, JSON outputs, and grounding visuals.

5. **Define Custom Schema**  
   Implement a `Product` model with fields like `product_name`, `brand`, numeric weights, and boolean claims (e.g., `is_organic`).

6. **Run ADE with Schema**  
   Re-run `parse(documents=file_paths, extraction_model=Product)` to get structured outputs.

7. **Convert to Table & Save**  
   Build a Pandas `DataFrame` from the structured results, display it, and save as `results_folder/output.csv`.

8. **Wrap‑Up**  
   Review results and reference ADE documentation for next steps.

## 🎯 Outputs

- **Markdown files** in `results_folder` for human-readable summaries  
- **JSON files** in `results_folder` with full extraction details  
- **CSV** (`output.csv`) containing structured field data  
- **Grounding visuals** in `groundings_folder`  

## 📚 Learn More

- ADE Documentation: https://docs.landing.ai/ade/ade-overview  
- Python Package: https://github.com/landing-ai/agentic-doc  
