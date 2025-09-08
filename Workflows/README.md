This section of the repo contains scripts for repeatable workflows. In most cases the workflows demonstrated here can be rapidly adpated to other use cases.

## Field Extraction
- **Apply a `pydantic` Schema to a Document to Extract Specific Fields as Key-Value Pairs**
  This workflow shows how to use the field extraction functionality with a `pydantic` shema. It applies a standard schema to a set of documents and returns a pandas dataframe with one row per document and one colum per request schema item.

## Batch Processing
- **Process all files in a folder with a UI**  
  This workflow provides a light-weight Streamlit front end for the non-technical user. The user selects a folder, and all files in the folder are sent to the Agentic Document Extraction API for processing. The returned results - document markdown, parsed chunks and visual groundings - are saved into folders. 

## Snowflake Integrations
- **High Volume Processing with Snowflake Insertion**  
  This workflow shows how to process large volumes of documents with the `agentic-doc` python library and stream the results into Snowflake tables and stages. Specifically, it parallelizes 50 documents and uses the `snowflake-connector` with threadpooling to insert the docuemtn extraction results into multiple Snowflake tables. 

## RAG Pipelines
- **RAG pipeline using ADE, OpenAI embeddings, and a local Chroma vector database**  
This repository demonstrates how to use LandingAI Agentic Document Extraction (ADE) with OpenAI embeddings and a local Chroma vector database to build a Retrieval-Augmented Generation (RAG) pipeline. It parses documents (e.g., SEC 10-K filings), extracts structured chunks, generates grounding visualizations, and enables local semantic search with grounding crops.

## Front-Ends for Document Extraction
- **Process all files in a folder with a UI**  
  This workflow provides a light-weight Streamlit front end for the non-technical user. The user selects a folder, and all files in the folder are sent to the Agentic Document Extraction API for processing. The returned results - document markdown, parsed chunks and visual groundings - are saved into folders. 

## Niche Workflows
- **SEC EDGAR Filings**  
  This workflow fetches 10-K and 8-K filings from the SEC's EDGAR database based on a stock ticker symbol.

