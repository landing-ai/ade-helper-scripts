# ADE + Snowflake Insertion Pipeline

This project demonstrates a complete pipeline that uses **LandingAI's Agentic Document Extraction (ADE)** to parse documents and insert structured data into **Snowflake** tables. It uses **invoices as an example**, but the pattern is modular and can be adapted to **any document type**.

Agentic Document Extraction offers complex layout extraction without layout-specific training, accurate extraction of tables and charts, and visual grounding for all extracted values, Learn more at [https://landing.ai/agentic-document-extraction](https://landing.ai/agentic-document-extraction).

LandingAI provides a [Visual Playground](https://va.landing.ai/demo/doc-extraction) with complimentary credits for new users. Use the Visual Playground to test performance on your own documents and develop your extrcation schema.

---

## 🚀 Features

- ✅ Parse diverse invoice formats using ADE with a schema-first approach
- ✅ Generate structured rows for header, line items, and visual context
- ✅ Automatically stage and insert to Snowflake tables
- ✅ Canary pipeline for spot-testing a single file
- ✅ Streaming bulk processing with wall clock + parse timing

---

## 📁 Project Structure

```bash
project/
├── ade_sf_pipeline_main.py   # Main orchestration logic
├── config.py                 # Centralized settings from .env
├── sf_utils.py              # Snowflake connection + utilities
├── doc_utils.py             # Page counting + utilities
├── metrics.py               # Timing + performance tracking
├── version_utils.py         # Resolve agentic-doc version
├── row_builder.py           # Converts parsed doc into row dicts
├── loader.py                # Buffered uploader and COPY logic
├── invoice_schema.py        # Pydantic schema for ADE parsing
└── ADE_with_Snowflake_Insertion_Main.ipynb # Demo notebook
```

---

## 🔧 What You Provide

To customize this pipeline for your own documents:

1. ✅ **A Pydantic schema** (like `InvoiceExtractionSchema`) for ADE to extract fields
2. ✅ **A `rows_from_doc()` function** to convert parsed docs to database rows
3. ✅ **Column lists** (`COLS_MAIN`, `COLS_LINES`) matching your Snowflake tables

Modify only:
- `invoice_schema.py`
- `row_builder.py`
- `loader.py`

---

## 🧪 Notebook Workflow

Open `ADE_with_Snowflake_Insertion_Main.ipynb` to:

1. Configure ADE + Snowflake via `.env` or Settings
2. Parse and insert a **canary document**
3. Stream and time a **bulk directory of documents**
4. View metrics and Snowflake results

---

## 🏗️ Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

You’ll need:
- `agentic-doc`
- `snowflake-connector-python`
- `pydantic`
- `python-dotenv`

### 2. Configure `.env` and `config.py``

Create a `.env` file following the example provided. See also [https://docs.landing.ai/ade/ade-retries#configuration-options](https://docs.landing.ai/ade/ade-retries#configuration-options)

See `config.py` for full list of available options.

### 3. Set up Snowflake

Examine the the SQL script included in this repo to create:

- File formats
- External stages
- Core tables
- A custom role with necessary privileges

---

## 📊 Output Tables

The following Snowflake tables will be populated:

- `INVOICES_MAIN` – Header fields like total, date, PO number
- `INVOICE_LINE_ITEMS` – Itemized rows (quantity, price, description)
- `PARSED_CHUNKS` – Visual chunks with page, box, and text
- `MARKDOWN` – Parsed markdown with visual grounding

---

## 🤝 Need Help?

- 📚 [ADE Docs](https://docs.landing.ai/ade/ade-overview)
- 🤖 [ADE Support Bot + Discord](https://docs.landing.ai/ade/ade-support)
- 🧱 [agentic-doc GitHub](https://github.com/landing-ai/agentic-doc)


