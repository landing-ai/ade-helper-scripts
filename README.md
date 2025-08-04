# 🧠 ADE Helper Scripts

This repository contains helper scripts, pipelines, and demo applications built around [LandingAI’s Agentic Document Extraction (ADE)](https://docs.landing.ai/ade/ade-overview). The goal is to showcase **document understanding workflows** across different domains (financial filings, CME certificates, batch processing apps) and make them reproducible for internal and partner teams.

---

## 📁 Repository Structure

```
ade-helper-script/
├── FinServ_Scripts/
│   ├── ADE_10K_Pipeline_Local/    # Local ADE + RAG pipeline for SEC 10-K filings
│   └── Edgar_API_Pipeline/        # Extracts and processes 10-Ks from SEC EDGAR
│
├── Streamlit_Application_Batch_Processing/
│   └── app.py                     # Webinar demo Streamlit app for batch document parsing
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🚀 Projects in This Repo

### 1. **Financial Services Pipelines**
- **ADE 10K Pipeline Local**  
  - Extracts financial metrics from 10-K filings.  
  - Runs ADE locally, saves outputs (`markdown`, `JSON`, visual grounding).  
  - Generates embeddings with OpenAI, stores in ChromaDB, supports **RAG (Retrieval-Augmented Generation)** querying with visual grounding.  

- **EDGAR API Pipeline**  
  - Downloads 10-Ks directly from the SEC EDGAR API.  
  - Prepares filings for ADE processing and downstream analysis.  

---

### 2. **Streamlit Batch Processing App**
Interactive web app (from LandingAI webinar) that:  
- Selects a local folder of documents.  
- Runs ADE on all PDFs/images.  
- Displays JSON outputs and page-level **bounding-box visualizations**.  
- Supports resetting/re-running without restarting the app.  

Run it with:
```bash
streamlit run Streamlit_Application_Batch_Processing/app.py
```

---

## 🔑 Setup

1. Clone this repo:
   ```bash
   git clone git@github.com:landing-ai/ade-helper-script.git
   cd ade-helper-script
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root:
   ```bash
   VISION_AGENT_API_KEY=your_ade_api_key
   OPENAI_API_KEY=your_openai_api_key
   ```

---

## 📦 Outputs

- **Markdown files** – human-readable ADE summaries  
- **JSON files** – structured extraction results  
- **Grounding images** – cropped visual evidence of extracted fields  
- **ChromaDB store** – local vector database for RAG queries  

---

## 🌐 Deployment on AWS (Optional)

For production, you can extend these workflows into a **serverless, event-driven pipeline**:
- **S3** – upload documents to trigger processing.  
- **Lambda** – run ADE parsing logic.  
- **OpenSearch** – store and query embeddings at scale.  
- **Bedrock (Claude, Titan)** – perform LLM-based RAG Q&A.  

---

## 📚 Learn More
- [LandingAI ADE Documentation](https://docs.landing.ai/ade/ade-overview)  
- [Agentic Document Extraction Playground](https://va.landing.ai/demo/doc-extraction)  
