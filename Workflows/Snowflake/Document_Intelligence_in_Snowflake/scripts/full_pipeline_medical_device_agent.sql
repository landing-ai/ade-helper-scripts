
--------------------------------------------------------------------------------
-- FDA MEDICAL DEVICE DOCUMENT INTELLIGENCE AGENT
-- Updated Jan 8 2026
--
-- This script builds a complete Cortex Agent that answers questions about FDA
-- medical device approval documents using LandingAI's Agentic Document
-- Extraction (ADE), Cortex Search, Cortex Analyst, and PubMed integration.
--
-- WHAT GETS CREATED:
--   • Database, schema, stages (with server-side encryption for presigned URLs)
--   • Warehouse for ADE processing
--   • Document parsing and extraction pipeline (via ADE API)
--   • Structured tables for extracted device metadata
--   • Cortex Search service over parsed document chunks
--   • Semantic view for natural language queries (Cortex Analyst)
--   • Stored procedure for generating presigned URLs
--   • Cortex Agent with multi-tool orchestration
--
-- PREREQUISITES:
--   • LandingAI Agentic Document Extraction app installed in your account
--   • ACCOUNTADMIN role (or equivalent CREATE/GRANT privileges)
--   • FDA medical device PDFs uploaded to stage after creation
--
-- IMPORTANT NOTES:
--   • Stage uses SNOWFLAKE_SSE encryption (required for presigned URLs)
--   • Script is idempotent - safe to re-run
--   • Sanity checks throughout help verify each step
--------------------------------------------------------------------------------


--------------------------------------------------------------------------------
-- SECTION 1: INITIAL SETUP - CORE INFRASTRUCTURE
-- This section creates the foundational Snowflake objects required for the
-- document intelligence pipeline (database, schema, stages, warehouse).
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

-- Use a role with sufficient privileges to create and grant objects.
-- ACCOUNTADMIN is recommended for initial bootstrap.
USE ROLE ACCOUNTADMIN;

-- Create the main database and schema for the FDA medical device application
CREATE DATABASE IF NOT EXISTS ADE_APPS_DB;
CREATE SCHEMA IF NOT EXISTS ADE_APPS_DB.FDA;

-- Create a stage to store PDF documents with directory listing enabled
-- This is where you'll upload your FDA medical device documents
-- IMPORTANT: Use SNOWFLAKE_SSE encryption for presigned URLs to work correctly
-- (files will be corrupted if client-side encryption is used)
CREATE STAGE IF NOT EXISTS ADE_APPS_DB.FDA.DOCS
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- NOTE: If you have an existing stage without server-side encryption, you must:
-- 1. CREATE STAGE ADE_APPS_DB.FDA.DOCS_NEW DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
-- 2. COPY FILES INTO @ADE_APPS_DB.FDA.DOCS_NEW FROM @ADE_APPS_DB.FDA.DOCS PATTERN = '.*';
-- 3. DROP STAGE ADE_APPS_DB.FDA.DOCS;
-- 4. ALTER STAGE ADE_APPS_DB.FDA.DOCS_NEW RENAME TO ADE_APPS_DB.FDA.DOCS;
-- 5. Re-grant permissions: GRANT READ, WRITE ON STAGE ADE_APPS_DB.FDA.DOCS TO APPLICATION "ADE";

-- Create a dedicated warehouse for ADE processing workloads
CREATE WAREHOUSE IF NOT EXISTS WH_LANDINGAI_ADE
    WITH WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 300
    AUTO_RESUME = TRUE;

-- Set working context to the newly created database and schema
USE DATABASE ADE_APPS_DB;
USE SCHEMA ADE_APPS_DB.FDA;

-- Create a stage for storing semantic models (used by Cortex Analyst)
CREATE STAGE IF NOT EXISTS ADE_APPS_DB.FDA.SEMANTIC_MODELS;

-- Enable Cortex features across all regions to allow cross-region AI functionality
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- Switch context to the ADE application to grant it necessary permissions
USE "ADE";

-- Grant the LandingAI ADE application access to the database, schema, and stage
-- This allows the app to read documents and write parse/extract results
GRANT USAGE ON DATABASE ADE_APPS_DB TO APPLICATION "ADE";
GRANT USAGE ON SCHEMA ADE_APPS_DB.FDA TO APPLICATION "ADE";
GRANT READ, WRITE ON STAGE ADE_APPS_DB.FDA.DOCS TO APPLICATION "ADE";

--------------------------------------------------------------------------------
-- SANITY CHECK: Verify files are staged correctly
-- IMPORTANT: Before proceeding, upload your PDF files to the /devices subfolder
-- in the ADE_APPS_DB.FDA.DOCS stage (best done via Snowflake UI)
--------------------------------------------------------------------------------

-- List all files in the stage to confirm they're uploaded correctly
LS @ADE_APPS_DB.FDA.DOCS;


--------------------------------------------------------------------------------
-- SECTION 2: DOCUMENT PARSING AND EXTRACTION
-- This section processes PDF documents using the ADE API to:
-- 1. Parse documents into structured chunks (text, tables, figures)
-- 2. Extract specific fields based on a JSON schema
--
-- ALTERNATIVE APPROACH: You can also use the ADE UI or follow the docs at:
-- https://docs.landing.ai/ade/ade-sf-parse-cloud
-- https://docs.landing.ai/ade/ade-sf-extract-cloud
--
-- REQUIRED FOR SETUP (This is the automated batch processing approach)
--------------------------------------------------------------------------------

-- Parse and extract all PDFs on the stage that match the filter criteria
-- This loop processes multiple documents automatically
DECLARE
    -- Cursor to select files from the stage based on size and naming pattern
    file_cursor CURSOR FOR
        SELECT RELATIVE_PATH
        FROM DIRECTORY(@ADE_APPS_DB.FDA.DOCS)
        WHERE SIZE < 1000000  -- Files smaller than 1MB (1,000,000 bytes)
            AND RELATIVE_PATH LIKE 'devices/P%.pdf'  -- Filter for FDA PMA documents
        LIMIT 10;  -- Adjust this limit based on how many files you want to process
    current_file_path STRING;
    full_stage_path STRING;

    parse_ret OBJECT;      -- Holds the parse API response
    extract_ret OBJECT;    -- Holds the extract API response

BEGIN
    -- Loop through each file matching the cursor criteria
    FOR file_record IN file_cursor DO
        current_file_path := file_record.RELATIVE_PATH;

        full_stage_path := '@"ADE_APPS_DB"."FDA"."DOCS"/' || :current_file_path;

        -- STEP 1: Parse the document into structured chunks (text, tables, figures)
        -- The parse API breaks down the PDF into semantic chunks with grounding info
        CALL api.parse(
            file_path => :full_stage_path,
            model => 'dpt-2-latest',  -- Latest document parsing transformer model
            output_table => 'medical_device_parse'  -- Output table (auto-created in ADE.DB schema)
        ) INTO :parse_ret;

        -- STEP 2: Extract specific fields using the parse result and a JSON schema
        -- This extracts structured data (device names, dates, summaries) from the chunks
        CALL api.extract(
            parse_result => :parse_ret,
            output_table => 'medical_device_extract',  -- Output table (auto-created in ADE.DB schema)
            model => 'extract-latest',
            schema => '{  -- JSON schema defines what fields to extract
            "title": "FDA Medical Device Stats",
            "type": "object",
            "properties": {
                "device_generic_name": { "type": "string", "description": "Generic device name from the SSED/labeling" },
                "device_trade_name":  { "type": "string", "description": "Marketed trade/brand name" },
                "applicant_name":     { "type": "string", "description": "Manufacturer/Sponsor/Applicant" },
                "applicant_address":  { "type": "string", "description": "Applicant mailing address as listed" },
        
                "premarket_approval_number": {
                  "type": "string",
                  "description": "Primary PMA (or De Novo/510(k)/HDE identifier), e.g., P200022"
                },
                "application_type": {
                  "type": "string",
                  "enum": ["PMA", "PMA_SUPPLEMENT", "DE_NOVO", "HDE", "510K"],
                  "description": "Submission type as stated"
                },
                "fda_recommendation_date": {
                  "type": "string",
                  "description": "Date of FDA review team/advisory panel recommendation, if stated and translated to YYYY-MM-DD"
                },
                "approval_date": {
                  "type": "string",
                  "description": "FDA approval decision date and translated to YYYY-MM-DD"
                },
            
                "indications_for_use": {
                  "type": "string",
                  "description": "Concise IFU statement (one paragraph)"
                },
            
                "key_outcomes_summary": {
                  "type": "string",
                  "description": "One-paragraph summary of pivotal effectiveness and safety (e.g., endpoint result, SAE highlights)"
                },
            
                "overall_summary": {
                  "type": "string",
                  "description": "Executive summary: what the device does, who it is for, key results, and benefit–risk conclusion"
                }
            },
              "required": [
                "device_generic_name",
                "device_trade_name",
                "applicant_name",
                "applicant_address",
                "premarket_approval_number",
                "approval_date",
                "overall_summary",
                "application_type",
                "fda_recommendation_date",
                "indications_for_use",
                "key_outcomes_summary"
              ],
              "additionalProperties": false
            }'
            
        ) INTO :extract_ret;
        
    END FOR;

END;

--------------------------------------------------------------------------------
-- SANITY CHECK: Inspect raw parse and extract results
-- These tables are created by the ADE API in the ADE.DB schema
--------------------------------------------------------------------------------

-- View all parsed chunks (text, tables, figures with grounding information)
SELECT * FROM DB.MEDICAL_DEVICE_PARSE;

-- View all extracted fields (structured data based on the JSON schema)
SELECT * FROM DB.MEDICAL_DEVICE_EXTRACT;

--------------------------------------------------------------------------------
-- SECTION 3: COPY RESULTS TO APPLICATION SCHEMA
-- Move the parse and extract results from the ADE.DB schema to your
-- application schema (ADE_APPS_DB.FDA) for downstream processing
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

-- Copy parsed chunks to the application schema with deduplication
CREATE OR REPLACE TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_PARSE AS
SELECT DISTINCT *
FROM ADE.DB.MEDICAL_DEVICE_PARSE;

-- Copy extracted fields to the application schema with deduplication
CREATE OR REPLACE TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACT AS
SELECT DISTINCT *
FROM ADE.DB.MEDICAL_DEVICE_EXTRACT;

--------------------------------------------------------------------------------
-- SANITY CHECK: Verify tables were copied correctly
--------------------------------------------------------------------------------

-- Inspect the copied parse table
SELECT * FROM ADE.DB.MEDICAL_DEVICE_PARSE;

-- Inspect the copied extract table
SELECT * FROM ADE.DB.MEDICAL_DEVICE_EXTRACT;

--------------------------------------------------------------------------------
-- SECTION 4: CREATE STRUCTURED TABLES FOR ANALYSIS
-- Transform the extracted JSON data into a clean, typed table structure
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

-- Create a flattened, typed table from the extracted JSON fields
-- This makes the data easier to query and use with Cortex Analyst
CREATE OR REPLACE TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACTED AS
SELECT
    EXTRACTION:applicant_address::STRING           AS APPLICANT_ADDRESS,
    EXTRACTION:applicant_name::STRING              AS APPLICANT_NAME,
    EXTRACTION:application_type::STRING            AS APPLICATION_TYPE,
    TRY_TO_DATE(EXTRACTION:approval_date::STRING)  AS APPROVAL_DATE,
    EXTRACTION:device_generic_name::STRING         AS DEVICE_GENERIC_NAME,
    EXTRACTION:device_trade_name::STRING           AS DEVICE_TRADE_NAME,
    EXTRACTION:indications_for_use::STRING         AS INDICATIONS_FOR_USE,
    EXTRACTION:key_outcomes_summary::STRING        AS KEY_OUTCOMES_SUMMARY,
    EXTRACTION:overall_summary::STRING             AS OVERALL_SUMMARY,
    EXTRACTION:premarket_approval_number::STRING   AS PREMARKET_APPROVAL_NUMBER
FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACT;

--------------------------------------------------------------------------------
-- SANITY CHECK: Verify structured data looks correct
--------------------------------------------------------------------------------

-- Inspect the flattened, typed table
SELECT * FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACTED;

--------------------------------------------------------------------------------
-- SECTION 5: PREPARE CHUNKS TABLE FOR CORTEX SEARCH
-- Flatten the parsed chunks and enrich with file metadata and stage URLs
-- This table will be used as the source for the Cortex Search service
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

-- Create a denormalized chunks table with one row per chunk
-- Includes grounding info (page, bounding box) and presigned URL helpers
CREATE OR REPLACE TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_CHUNKS AS
WITH FILE_MAP AS (
    SELECT
        RELATIVE_PATH,
        -- basename, e.g. 'P230014B.pdf'
        REGEXP_SUBSTR(RELATIVE_PATH, '[^/]+$') AS BASENAME
    FROM DIRECTORY(@ADE_APPS_DB.FDA.DOCS)
),
PARSE_WITH_PATH AS (
    SELECT
        p.DOC_ID,
        p.SOURCE_URL,
        p.FILENAME,
        p.PAGE_COUNT,
        p.PARSED_AT,
        p.CHUNKS,
        m.RELATIVE_PATH
    FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_PARSE p
    JOIN FILE_MAP m
      ON m.BASENAME = p.FILENAME
)
SELECT
    p.DOC_ID,
    p.FILENAME,
    p.SOURCE_URL,
    p.PAGE_COUNT,
    p.PARSED_AT,
    p.RELATIVE_PATH,

    c.INDEX::INTEGER AS CHUNK_INDEX,
    c.VALUE          AS CHUNK_INFO,

    -- chunk fields (per ade json response)
    c.VALUE:id::STRING       AS CHUNK_ID,
    c.VALUE:type::STRING     AS CHUNK_TYPE,
    c.VALUE:markdown::STRING AS CHUNK_MARKDOWN,

    -- grounding fields (grounding is an object with page + box)
    c.VALUE:grounding:page::INTEGER AS PAGE_NUMBER,
    c.VALUE:grounding:box::VARIANT  AS CHUNK_BOX,

    -- stage helpers
    '@ADE_APPS_DB.FDA.DOCS' AS STAGE_NAME,
    '@ADE_APPS_DB.FDA.DOCS/' || p.RELATIVE_PATH AS FULL_PATH,
    BUILD_SCOPED_FILE_URL('@ADE_APPS_DB.FDA.DOCS', p.RELATIVE_PATH) AS FILE_URL

FROM PARSE_WITH_PATH p,
LATERAL FLATTEN(INPUT => p.CHUNKS) c
;

--------------------------------------------------------------------------------
-- SANITY CHECK: Verify chunks table structure
--------------------------------------------------------------------------------

-- Inspect the chunks table (should have one row per chunk with metadata)
SELECT * FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_CHUNKS;


--------------------------------------------------------------------------------
-- SECTION 6: CREATE CORTEX SEARCH SERVICE
-- Set up a Cortex Search service to enable semantic search over document chunks
-- This allows the agent to find relevant passages to answer user questions
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

-- Enable change tracking so Cortex Search can incrementally update the index
ALTER TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_CHUNKS
SET CHANGE_TRACKING = TRUE;

-- Create the Cortex Search service
-- This indexes the CHUNK_MARKDOWN field and makes other fields available as attributes
-- You can also create this via the UI: AI & ML -> Cortex Search
CREATE OR REPLACE CORTEX SEARCH SERVICE ADE_APPS_DB.FDA.FDA_DOCUMENT_SEARCH
    ON CHUNK_MARKDOWN
    ATTRIBUTES RELATIVE_PATH, FULL_PATH, FILE_URL, FILENAME, DOC_ID, PAGE_NUMBER, CHUNK_ID, CHUNK_TYPE
    WAREHOUSE = 'WH_LANDINGAI_ADE'
    TARGET_LAG = '1 DAY'
AS
(
    SELECT
        CHUNK_MARKDOWN,
        RELATIVE_PATH,
        FULL_PATH,
        FILE_URL,
        FILENAME,
        DOC_ID,
        PAGE_NUMBER,
        CHUNK_INDEX,
        CHUNK_INFO,
        CHUNK_ID,
        CHUNK_TYPE,
        CHUNK_BOX,
        STAGE_NAME
    FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_CHUNKS
);

--------------------------------------------------------------------------------
-- SANITY CHECK: Test the Cortex Search service
-- Verify that the search service is working and returning relevant results
--------------------------------------------------------------------------------

-- Test query: Search for chunks related to "intended use of the medical device"
-- This should return the top 10 most relevant chunks with their metadata
WITH RESP AS (
  SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
      'ADE_APPS_DB.FDA.FDA_DOCUMENT_SEARCH',
      '{
        "query": "intended use of the medical device",
        "columns": [
          "CHUNK_MARKDOWN",
          "RELATIVE_PATH",
          "PAGE_NUMBER",
          "CHUNK_INDEX",
          "CHUNK_ID",
          "FILE_URL"
        ],
        "limit": 10
      }'
    )
  ) AS J
)
SELECT
  R.VALUE:CHUNK_MARKDOWN::STRING AS CHUNK_TEXT,
  R.VALUE:RELATIVE_PATH::STRING  AS RELATIVE_PATH,
  R.VALUE:PAGE_NUMBER::INTEGER   AS PAGE_NUMBER,
  R.VALUE:CHUNK_INDEX::INTEGER   AS CHUNK_INDEX,
  R.VALUE:CHUNK_ID::STRING       AS CHUNK_ID,
  R.VALUE:FILE_URL::STRING       AS FILE_URL
FROM RESP,
LATERAL FLATTEN(INPUT => J['results']) R;

--------------------------------------------------------------------------------
-- SECTION 7: CREATE SEMANTIC VIEW FOR CORTEX ANALYST
-- Define a semantic layer that maps business-friendly terms to database columns
-- This allows Cortex Analyst to translate natural language questions into SQL
-- You can also create/edit this via the UI: AI & ML -> Cortex Analyst
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

-- Create a semantic view with business-friendly column descriptions and synonyms
-- This enables natural language queries like "What devices were approved in 2024?"

CREATE OR REPLACE SEMANTIC VIEW ADE_APPS_DB.FDA.MEDICAL_DEVICES
  TABLES (
    ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACTED
  )
  DIMENSIONS (
    MEDICAL_DEVICE_EXTRACTED.APPLICANT_ADDRESS AS APPLICANT_ADDRESS
      WITH SYNONYMS = ('applicant_location','company_address','business_address','organization_location','registrant_address','submitter_address','manufacturer_address')
      COMMENT = 'The street address of the applicant, including the company name, street number, city, state, and zip code.',

    MEDICAL_DEVICE_EXTRACTED.APPLICANT_NAME AS APPLICANT_NAME
      WITH SYNONYMS = ('applicant','applicant_full_name','applicant_title','company_name','organization_name','submitter_name','registrant_name','manufacturer_name')
      COMMENT = 'The name of the company or organization that submitted the medical device for approval or clearance.',

    MEDICAL_DEVICE_EXTRACTED.APPLICATION_TYPE AS APPLICATION_TYPE
      WITH SYNONYMS = ('application_category','submission_type','filing_classification','request_format','application_classification','submission_category','filing_type')
      COMMENT = 'The type of application submitted to the FDA for approval of a medical device, where PMA (Premarket Approval) is for new devices and PMA SUPPLEMENT is for modifications to an existing approved device.',

    MEDICAL_DEVICE_EXTRACTED.APPROVAL_DATE AS APPROVAL_DATE
      WITH SYNONYMS = ('approval_timestamp','certification_date','clearance_date','date_approved','date_cleared','date_certified','authorized_date','verified_date')
      COMMENT = 'The date on which the medical device was approved for use.',

    MEDICAL_DEVICE_EXTRACTED.DEVICE_GENERIC_NAME AS DEVICE_GENERIC_NAME
      WITH SYNONYMS = ('generic_device_name','device_common_name','nonproprietary_name','device_identifier','common_device_name','device_description')
      COMMENT = 'The DEVICE_GENERIC_NAME column contains the generic name of a medical device, which is a general term that describes the device''s function or purpose, and is often used to categorize or group similar devices together.',

    MEDICAL_DEVICE_EXTRACTED.DEVICE_TRADE_NAME AS DEVICE_TRADE_NAME
      WITH SYNONYMS = ('brand_name','product_name','device_brand','trade_name','product_title','commercial_name','proprietary_name')
      COMMENT = 'The name of the medical device as it is commercially known or branded.',

    MEDICAL_DEVICE_EXTRACTED.INDICATIONS_FOR_USE AS INDICATIONS_FOR_USE
      WITH SYNONYMS = ('intended_use','purpose','intended_purpose','indications','usage_indications','intended_applications','medical_indications','device_indications','use_indications')
      COMMENT = 'This column contains the indications for use for various medical devices, including their intended purposes, target patient populations, and any relevant contraindications or warnings.',

    MEDICAL_DEVICE_EXTRACTED.KEY_OUTCOMES_SUMMARY AS KEY_OUTCOMES_SUMMARY
      WITH SYNONYMS = ('key_findings','main_results','summary_of_key_results','key_trial_outcomes','major_outcomes','trial_summary','key_study_results','main_study_findings')
      COMMENT = 'This column contains summaries of key outcomes from clinical trials and studies for various medical devices, including survival rates, adverse event rates, and effectiveness endpoints, providing an overview of the devices'' performance and safety.',

    MEDICAL_DEVICE_EXTRACTED.OVERALL_SUMMARY AS OVERALL_SUMMARY
      WITH SYNONYMS = ('general_summary','summary_overview','overall_description','brief_summary','summary_report','executive_summary')
      COMMENT = 'This column contains a detailed summary of the medical device, including its intended use, clinical trial results, benefits, and risks, providing a comprehensive overview of the device''s safety and effectiveness.',

    MEDICAL_DEVICE_EXTRACTED.PREMARKET_APPROVAL_NUMBER AS PREMARKET_APPROVAL_NUMBER
      WITH SYNONYMS = ('premarket_approval_code','pma_number','premarket_approval_id','premarket_clearance_number','fda_approval_number','premarket_authorization_number')
      COMMENT = 'Unique identifier assigned by the FDA to a medical device that has been approved for marketing through the premarket approval (PMA) process.'
  )
  COMMENT = 'This semantic view captures key information about medical devices submitting premarket approval applications to the FDA.'
  WITH EXTENSION (
  CA='{
    "tables": [
      {
        "name": "MEDICAL_DEVICE_EXTRACTED",
        "dimensions": [
          { "name": "APPLICANT_NAME" },
          { "name": "DEVICE_TRADE_NAME" },
          { "name": "APPLICATION_TYPE" },
          { "name": "APPROVAL_DATE" }
        ]
      }
    ],
    "verified_queries": [
      {
        "name": "Most recent FDA approval",
        "question": "What is the most recent medical device approved?",
        "sql": "SELECT DEVICE_TRADE_NAME, DEVICE_GENERIC_NAME, APPLICANT_NAME, APPROVAL_DATE FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACTED ORDER BY APPROVAL_DATE DESC NULLS LAST LIMIT 1"
      },
      {
        "name": "Devices by applicant",
        "question": "How many devices has each applicant submitted?",
        "sql": "SELECT APPLICANT_NAME, COUNT(*) AS DEVICE_COUNT FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACTED GROUP BY APPLICANT_NAME ORDER BY DEVICE_COUNT DESC"
      }
    ]
  }'
);

--------------------------------------------------------------------------------
-- SECTION 8: CREATE PRESIGNED URL STORED PROCEDURE
-- This stored procedure generates temporary browser-accessible URLs for files
-- in the stage, allowing the agent to provide document download links to users
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

USE DATABASE ADE_APPS_DB;
USE SCHEMA ADE_APPS_DB.FDA;

-- Create a stored procedure that generates presigned URLs with configurable expiration
CREATE OR REPLACE PROCEDURE ADE_APPS_DB.FDA.GET_FILE_PRESIGNED_URL_SP(
    RELATIVE_FILE_PATH STRING,
    EXPIRATION_MINS INTEGER DEFAULT 60
)
RETURNS STRING
LANGUAGE SQL
COMMENT = 'Generates a presigned url for a file in @ADE_APPS_DB.FDA.DOCS. Input is the relative file path (e.g., devices/P230043B.pdf).'
EXECUTE AS CALLER
AS
$$
DECLARE
    presigned_url STRING;
    sql_stmt STRING;
    expiration_seconds INTEGER;
    stage_name STRING DEFAULT '@ADE_APPS_DB.FDA.DOCS';
BEGIN
    expiration_seconds := EXPIRATION_MINS * 60;

    sql_stmt := 'SELECT GET_PRESIGNED_URL('
                || stage_name
                || ', '''
                || RELATIVE_FILE_PATH
                || ''', '
                || expiration_seconds
                || ') AS url';

    EXECUTE IMMEDIATE :sql_stmt;

    SELECT "URL"
      INTO :presigned_url
      FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

    RETURN :presigned_url;
END;
$$;

--------------------------------------------------------------------------------
-- SECTION 9: CREATE THE CORTEX AGENT
-- Define the agent with its profile, instructions, tools, and tool resources
-- The agent orchestrates queries across structured data (Cortex Analyst),
-- document search (Cortex Search), PubMed articles, and dynamic URLs
-- You can also create/edit this via the UI: AI & ML -> Agents
-- REQUIRED FOR SETUP
--------------------------------------------------------------------------------

-- Create the agent with comprehensive configuration

CREATE OR REPLACE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.LANDINGAI_ADE_MEDICAL_DEVICE
WITH PROFILE = '{
  "display_name": "LandingAI ADE Medical Device Agent",
    "avatar": "📄",
  "color": "#2563EB"
}'
COMMENT = $$ Use this Agent to interact with FDA medical device safety and effectiveness summaries which exist in a Snowflake stage and have been parsed with Agentic Document Extraction. This Agent also has access to PubMed research articles for background and context on these devices.$$
FROM SPECIFICATION $$
{
  "models": { "orchestration": "auto" },
  "instructions": {
    "response": "Be concise, use bullet points where helpful, and always include citations for factual claims. When presenting tables or figures, summarize the key takeaway before quoting values. When citing sources, label them clearly as either FDA Document or PubMed Article. Cite each source only once per answer.",
    "system": "You are an expert assistant for FDA medical device analysis. You must ground all claims in FDA approval documents or PubMed citations. Do not speculate beyond the provided sources. If the answer is not supported by available documents, say so.",
    "orchestration": "When the user asks about FDA medical devices, first query the database using the medical device lookup and then use the FDA Document search Cortex Search service to find relevant passages for the specific device. When the user asks for supporting source text or document evidence, use the fda_document_search tool to retrieve relevant chunks. Deduplicate retrieved chunks by CHUNK_ID. Prefer table and figure chunks (CHUNK_TYPE='table' or CHUNK_TYPE='figure') when the question involves numeric values, incidence rates, percentages, or counts. If the user asks for biomedical background or published evidence beyond FDA submissions, use PUBMED_BIOMEDICAL_RESEARCH_CORPUS and cite those articles separately from FDA documents. Only when the user explicitly asks to open, view, or download a document, call the Dynamic_Doc_URL_Tool to generate a temporary, browser-accessible URL. Do not return Snowflake internal /api/files URLs.",
    "sample_questions": [
    {
      "question": "Return a table listing all the devices in the database with their generic name, trade name, manufacturerpremarket approval number, and approval date.",
      "answer": "I'll query the extracted device table and return the most recent approval date with the device name."
    },
    {
      "question": "What is the most recent FDA-approved medical device in this dataset?",
      "answer": "I'll query the extracted device table and return the most recent approval date with the device name."
    },
    {
      "question": "According to FDA filings, what are the indications for use for the EXCOR Pediatric Ventricular Assist Device?",
      "answer": "I'll retrieve the relevant FDA chunks (prioritizing indications sections and tables) and summarize the indications with citations."
    },
    {
      "question": "What sizes are available for the EXCOR pediatric pump?",
      "answer": "I'll locate the section or table in the FDA filing that lists pump sizes and report them with citations."
    },
    {
        "question": "Print the chunks used as sources for the question about pump sizes. Also print the chunk reference ids.",
        "answer": "Here are the source chunks that were used to answer your question."
    },
    {
        "question": "Summarize the Kaplan-Meier freedom-from-death curve for all implant groups for the EXCOR pediatric pump.",
        "answer": "Based on the FDA approval document, here is a summary of the Kaplan-Meier freedom-from-death curve for all implant groups."
    },
    {
      "question": "Find peer-reviewed evidence about bleeding events in pediatric ventricular assist devices.",
      "answer": "I'll search PubMed, summarize the most relevant findings, and cite the returned articles separately from FDA documents."
    },
    {
      "question": "Open the FDA approval document for P160035B.",
      "answer": "I'll locate the document and generate a temporary browser link using the Dynamic_Doc_URL_Tool."
    }
  ]
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "medical_device_lookup",
        "description": "Semantic view over FDA medical device extracted fields (applicant, device names, approval dates, summaries, etc.)."
      }
    },
    {
      "tool_spec": {
        "type": "cortex_search",
        "name": "fda_document_search",
        "description": "Looks up medical device approval documents containing full submitted contents (chunk-level search)."
      }
    },
    {
      "tool_spec": {
        "type": "cortex_search",
        "name": "PUBMED_BIOMEDICAL_RESEARCH_CORPUS",
        "description": "Biomedical research articles from PubMed Central (via Snowflake Cortex Knowledge Extensions)."
      }
    },
    {
      "tool_spec": {
        "type": "generic",
        "name": "Dynamic_Doc_URL_Tool",
        "description": "Generates a temporary URL for a document in the stage given its relative file path (for example: devices/P230043B.pdf).",
        "input_schema": {
          "type": "object",
          "properties": {
            "expiration_mins": { "description": "expiration in minutes", "type": "number" },
            "relative_file_path": { "description": "relative file path inside the stage (e.g., devices/P230043B.pdf)", "type": "string" }
          },
          "required": ["expiration_mins", "relative_file_path"]
        }
      }
    }
  ],
  "tool_resources": {
    "Dynamic_Doc_URL_Tool": {
      "execution_environment": { "query_timeout": 274, "type": "warehouse", "warehouse": "WH_LANDINGAI_ADE" },
      "identifier": "ADE_APPS_DB.FDA.GET_FILE_PRESIGNED_URL_SP",
      "name": "GET_FILE_PRESIGNED_URL_SP(VARCHAR, DEFAULT NUMBER)",
      "type": "procedure"
    },
    "fda_document_search": {
      "id_column": "RELATIVE_PATH",
      "max_results": 6,
      "name": "ADE_APPS_DB.FDA.FDA_DOCUMENT_SEARCH",
      "title_column": "RELATIVE_PATH"
    },
    "medical_device_lookup": {
      "execution_environment": { "query_timeout": 300, "type": "warehouse", "warehouse": "WH_LANDINGAI_ADE" },
      "semantic_view": "ADE_APPS_DB.FDA.MEDICAL_DEVICES"
    },
    "PUBMED_BIOMEDICAL_RESEARCH_CORPUS": {
      "id_column": "ARTICLE_URL",
      "max_results": 6,
      "name": "PUBMED_BIOMEDICAL_RESEARCH_CORPUS.OA_COMM.PUBMED_OA_CKE_SEARCH_SERVICE",
      "title_column": "ARTICLE_CITATION"
    }
  }
}
$$;

--------------------------------------------------------------------------------
-- SANITY CHECKS: Test all components end-to-end
-- Run these queries to verify the entire pipeline is working correctly
--------------------------------------------------------------------------------

-- Test 1: Verify Cortex Search is working end-to-end
-- This should return relevant chunks about device indications
WITH RESP AS (
  SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
      'ADE_APPS_DB.FDA.FDA_DOCUMENT_SEARCH',
      '{
        "query": "the device is indicated for",
        "columns": ["CHUNK_MARKDOWN","RELATIVE_PATH","PAGE_NUMBER"],
        "limit": 5
      }'
    )
  ) AS J
)
SELECT
  R.VALUE:CHUNK_MARKDOWN::STRING AS TEXT,
  R.VALUE:RELATIVE_PATH::STRING  AS FILE,
  R.VALUE:PAGE_NUMBER::INTEGER   AS PAGE
FROM RESP,
LATERAL FLATTEN(INPUT => J['results']) R;


-- Test 2: Verify the presigned URL stored procedure works
-- This should return a temporary URL that you can open in a browser
CALL ADE_APPS_DB.FDA.GET_FILE_PRESIGNED_URL_SP('devices/P160048S021B.pdf', 60);

--------------------------------------------------------------------------------
-- FINAL NOTES: PERMISSIONS AND USAGE
--------------------------------------------------------------------------------

-- Since we used ACCOUNTADMIN, make sure to grant necessary permissions to roles
-- that will interact with the agent, including:
--   - USAGE on the database, schema, and warehouse
--   - READ on tables and stages
--   - USAGE on Cortex Search services and Agents

-- To interact with the agent:
-- Navigate to ai.snowflake.com, find your agent, and start asking questions!
-- The agent can answer questions about devices, search documents, cite PubMed
-- articles, and generate download links for FDA documents.