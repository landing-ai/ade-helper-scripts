# Agentic Document Extraction (ADE) from LandingAI

This repo contains many end-to-end examples that make use of ADE. These examples are intended to **complement the official product documentation** located at [https://docs.landing.ai/ade/ade-overview](https://docs.landing.ai/ade/ade-overview).


The repo is organized as follows:

- **Workflows**: Code-based examples of common workflows that include ADE. These are appropriate for all industries and use cases. They show how to use the ADE APIs in production via easy-to-understand sample documents. Adapt these standard workflows for your own needs. Inside you will find:
    - Field Extraction Workflows
    - Retrieval Augmented Generation (RAG) Workflows
    - Snowflake-specific Workflows
    - Specialized Workflows (Large files, AWS Lambda, Streamlit, etc.)
- **Events**: Code that is created specifically for events such as conference presentations, webinars or Hackathons. If you saw a great demo at an event, this is where you will find the details.
- **Industry Use Cases**: Items in this section are 80%+ complete solutions for specific use cases. The items in this section include subject matter expertise surrounding the particular use case.
- **Functional Area Use Cases**: Items in this section are 80%+ complete solutions for specific use cases in functional areas such as HR or Corporate Finance. The items in this section include subject matter expertise surrounding the particular use case.


## Full Repo Contents

Sometimes it is hard to decide where to 'file' a particular resource in the folder structure. We don't want you to miss a great piece of content and have to reinvent the wheel, so here is a full list of resources.

|Level| Title | Last Updated | Author | Tags |
|-----|-----|-----|-----|-----|
|**EVENTS**|||||
|Intermediate|[Deep Learning AI Dev Day 2025 Demo](https://github.com/landing-ai/ade-helper-scripts/tree/main/Events/Deeplearning_Event_FY25)|11/2025|David Park|ADE Parse, ADE Extract, mixed document types, visualizations, DPT-2|
|**WORKFLOWS - Field Extraction**|||||
|Beginner|[ADE Parse and Extract with Python](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/ADE_Parse_and_Extract_with_Python)|10/2025|Andrea Kropp|ADE Parse, ADE Extract, DPT-2|
|Beginner|[Basic Field Extraction using Product Images](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Field_Extraction/Basic_Field_Extraction_using_Product_Images)|11/2025|Andrea Kropp|ADE Parse, ADE Extract, food labels, DPT-2|
|Intermediate|[Classify Extract Visualize Workflow](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Field_Extraction/Classify_Extract_Visualize_Workflow)|11/2025 |Day Fernandes|ADE Parse, ADE Extract,mixed document types, document classification, visualizations|
|**WORKFLOWS - RAG**|||||
|Beginner|[Document Parser for RAG Applications](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Retrieval_Augmented_Generation/Chunking_for_RAG_Applications)|10/2025|Andrea Kropp|ADE Parse, RAG, chunking, DPT-2|
|Intermediate|[ADE Local RAG with OpenAI and ChromaDB](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Retrieval_Augmented_Generation/ADE_Local_RAG_OpenAI_ChromaDB)|9/2025|David Park|ADE Parse, RAG, ChromaDB, OpenAI embeddings, 10-K filings, DPT-1|
|Intermediate|[ADE LLM Retrieval Workflow](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/ADE_LLM_Retrieval)|9/2025|David Park|ADE Parse, RAG, LLM integration,  FAISS, evaluation, DPT-1|
|**WORKFLOWS - Special Cases**|||||
|Beginner|[Parse Jobs API for Large Files](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Parse_Jobs_API_for_Large_Files)|10/2025|Ava Xia|ADE Parse Jobs, async processing, large files|
|Intermediate|[ADE Lambda S3 - Serverless Document Processing](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/ADE_Lambda_S3)|9/2025|Ava Xia|AWS Lambda, Docker, serverless, batch processing, DPT-1|
|Intermediate|[Streamlit Frontend for ADE](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Front_End_Creation/Streamlit_Application_Batch_Processing)|8/2025|Andrea Kropp|ADE Parse, Streamlit, batch processing, user interface, DPT-1|
|Intermediate|[Word-Level_Grounding](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Word-Level_Grounding)|12/2025|David Park|ADE Parse, ADE Extract, Visual Grounding, DPT-2, and Word-Level Grounding using OCR + Fuzzy Matching|
|**WORKFLOWS - Snowflake**|||||
|Advanced|[High Volume ADE with Snowflake Insertion](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Snowflake/High_Volume_ADE_with_Snowflake_Insertion)|9/2025|Andrea Kropp|ADE Parse, ADE Extract, Snowflake, invoices, batch processing, DPT-1|
|Advanced|[Document Intelligence in Snowflake](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/Snowflake/Document_Intelligence_in_Snowflake)|9/2025|Randy Petus (Snowflake)|Snowflake Cortex, Cortex Search, Cortex Analyst, Cortex Agents, RAG|
|**INDUSTRY USE CASES - Financial Services**|||||
|Beginner|[Automated Utility Bill Parsing](https://github.com/landing-ai/ade-helper-scripts/tree/main/Industry_Use_Cases/Financial%20Services/Utility_Bills)|9/2025|Andrea Kropp|ADE Parse, ADE Extract, utility bills, schema provided, DPT-1|
|**FUNCTIONAL AREA USE CASES - HR**|||||
|Beginner|[Automated Continuing Education Certificate Parsing](https://github.com/landing-ai/ade-helper-scripts/tree/main/Functional_Area_Use_Cases/HR/Continuing_Education_Certificates)|9/2025|Andrea Kropp|ADE Parse, ADE Extract, HR, continuing education, compliance tracking, schema provided|
|**FUNCTIONAL AREA USE CASES - Corporate Finance**|||||
|Beginner|[Automated Invoice Parsing](https://github.com/landing-ai/ade-helper-scripts/tree/main/Workflows/ADE_Parse_and_Extract_with_Python)|11/2025|Andrea Kropp|ADE Parse, ADE Extract, invoices, schema provided, DPT-2|

## End Note

All of the code in the repo is provided as-is. We try to keep all the examples as current as possible, but you may find things that don't work or are outdated as you explore.
