# ADE 10-K Processing with Local RAG

This repository demonstrates how to use **LandingAI Agentic Document Extraction (ADE)** with **OpenAI embeddings** and a local **Chroma vector database** to build a Retrieval-Augmented Generation (RAG) pipeline.

It parses documents (e.g., SEC 10-K filings), extracts structured chunks, generates grounding visualizations, and enables local semantic search with grounding crops.

---

## Features

- **Agentic Document Extraction (ADE)**  
  Extracts text, tables, and metadata into JSON + Markdown.  
  Generates grounding crops and bounding box visualizations.

- **Chroma Vector Database**  
  Stores document chunks with OpenAI embeddings for fast semantic search.  
  Fully local persistence (`./chroma_db`).

- **Retrieval with Grounding**  
  Query in natural language → retrieve top chunks with similarity scores.  
  Optionally display grounding crops showing where the content came from.

---

## Quickstart

### 1. Clone Repository
```bash
git clone https://github.com/your-username/ADE-10K-RAG.git
cd ADE-10K-RAG
```

### 2. Create Environment
```bash
conda create -n ade_rag python=3.11 -y
conda activate ade_rag
pip install -r requirements.txt
```

### 3. Configure API Keys
Create a `.env` file at the project root:

```env
# LandingAI ADE API Key
VISION_AGENT_API_KEY=your_landingai_key_here

# OpenAI Key (for embeddings + optional LLM)
OPENAI_API_KEY=your_openai_key_here
```

### 4. Run Notebook
Open JupyterLab and run the pipeline:

```bash
jupyter lab
```

Notebook: **`ADE_10K_Processing_Local.ipynb`**

This will:
- Parse `apple_10k.pdf`
- Save outputs to `ade_outputs/`
- Store embeddings in `chroma_db/`
- Enable interactive RAG querying with grounding crops

---

## Directory Layout

```
ADE-10K-RAG/
├── ADE_10K_Processing_Local.ipynb   # Main pipeline notebook
├── apple_10k.pdf                    # Sample 10-K
├── summary_20250711_153127.txt      # Example summary (from EDGAR pipeline)
├── ade_outputs/                     # ADE outputs (json, markdown, crops, viz)
├── chroma_db/                       # Persistent local Chroma DB
├── .env                             # API keys (not committed)
├── README.md
└── requirements.txt
```

---

## Example Query

```python
rag_query("What was Apple’s net sales in 2023?", top_k=3, threshold=0.25)
```

Output:
- Retrieved text snippet
- Similarity score
- Grounding crop image (if available)

---

## Requirements

See [requirements.txt](./requirements.txt).

Tested with:
- Python 3.11
- JupyterLab
- macOS / Linux

---
