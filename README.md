# 🧠 ADE Helper Scripts

This repository contains helper scripts, pipelines, and demo applications built around [LandingAI’s Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview). The goal is to showcase **document understanding workflows** across different domains (financial filings, CME certificates, batch processing apps) and make them reproducible for internal and partner teams.

## ⚠️ Disclaimer
All sample helper scripts are provided **“as is”** for use with Agentic Document Extraction (ADE).  
No warranty is expressed or implied, and no support is provided.

---

## 📁 Repository Structure

```
ade-helper-script/
├── Industry_Use_Cases/
│   └── FinServ_Scripts/
│       ├── ADE_10K_Pipeline_Local/    # Local ADE + RAG pipeline for SEC 10-K filings
│       └── Edgar_API_Pipeline/        # Extracts and processes 10-Ks from SEC EDGAR
│
├── Workflows/
│   └── Streamlit_Application_Batch_Processing/
│       └── app.py                     # Webinar demo Streamlit app for batch document parsing
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🚀 Projects in This Repo

### 1. **Industry Use Cases**
- **Financial Services Pipelines**
  - **ADE 10K Pipeline Local**  
    - Extracts financial metrics from 10-K filings.  
    - Runs ADE locally, saves outputs (`markdown`, `JSON`, visual grounding).  
    - Generates embeddings with OpenAI, stores in ChromaDB, supports **RAG (Retrieval-Augmented Generation)** querying with visual grounding.  

  - **EDGAR API Pipeline**  
    - Downloads 10-Ks directly from the SEC EDGAR API.  
    - Prepares filings for ADE processing and downstream analysis.  

---

### 2. **Workflows**
- **Streamlit Batch Processing App**  
  Interactive web app (from LandingAI webinar) that:  
  - Selects a local folder of documents.  
  - Runs ADE on all PDFs/images.  
  - Displays JSON outputs and page-level **bounding-box visualizations**.  
  - Supports resetting/re-running without restarting the app.  

  Run it with:
  ```bash
  streamlit run Workflows/Streamlit_Application_Batch_Processing/app.py
  ```

---

## 📚 Learn More
- [LandingAI ADE Documentation](https://docs.landing.ai/ade/ade-overview)  
- [Agentic Document Extraction Playground](https://va.landing.ai/demo/doc-extraction)  
