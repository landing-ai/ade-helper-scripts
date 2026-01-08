


--------------------------------------------------------------------------------
-- UPDATED January 7 2026
--
-- PURPOSE
-- This script bootstraps all Snowflake objects required for:
--   - Agentic Document Extraction (ADE)
--   - Document ingestion and parsing
--   - Secure access to stages, tables, and stored procedures
--
-- WHAT THIS SCRIPT SETS UP:
--   1. Execution context (role, warehouse, database, schema)
--   2. Core database and schema objects
--   3. Supporting infrastructure used by the ADE Native App
--
-- WHO SHOULD RUN THIS:
--   • Snowflake account administrators
--   • Platform or data engineers responsible for ADE setup
--
-- ASSUMPTIONS:
--   • Agentic Document Extraction from LandingAI is already installed in the Snowflake account
--   • The executing role has CREATE / GRANT privileges
--   • This script may be re-run safely (idempotent where possible)
--
-- NOTES:
--   • Object names are intentionally explicit for clarity
--   • Comments focus on intent ("why") rather than SQL mechanics
--------------------------------------------------------------------------------



-- use a role with sufficient privileges to create and grant objects.
USE ROLE ACCOUNTADMIN;

-- create snowflake objects
CREATE DATABASE IF NOT EXISTS ADE_APPS_DB;
CREATE SCHEMA IF NOT EXISTS ADE_APPS_DB.FDA;
CREATE STAGE IF NOT EXISTS ADE_APPS_DB.FDA.DOCS
    DIRECTORY = (ENABLE = TRUE);

CREATE WAREHOUSE IF NOT EXISTS WH_LANDINGAI_ADE
    WITH WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 300
    AUTO_RESUME = TRUE;

USE DATABASE ADE_APPS_DB;
USE SCHEMA ADE_APPS_DB.FDA;

CREATE STAGE IF NOT EXISTS ADE_APPS_DB.FDA.SEMANTIC_MODELS;

-- enable cross region cortex
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

USE "ADE";

-- grant LandingAI app access to db, schema and stage

GRANT USAGE ON DATABASE ADE_APPS_DB TO APPLICATION "ADE";
GRANT USAGE ON SCHEMA ADE_APPS_DB.FDA TO APPLICATION "ADE";
GRANT READ, WRITE ON STAGE ADE_APPS_DB.FDA.DOCS TO APPLICATION "ADE";

-- IMPORTANT: put your files in the /devices stage subfolder to align with the rest of this flow
-- this is best done in the Snowflake UI

-- list files in the stage
LS @ADE_APPS_DB.FDA.DOCS;

------ NO LONGER NEEDED --------
-- create the table to land extracted document contents
create table if not exists ade_apps_db.fda.medical_device_docs (
    relative_path varchar,
    file_contents variant,
    stage_name varchar,
    last_modified timestamp_tz
);
------ NO LONGER NEEDED --------

-- follow instructions at https://docs.landing.ai/ade/ade-sf-parse-cloud and https://docs.landing.ai/ade/ade-sf-extract-cloud
-- to parse multiple staged files and extract structured fields based on a schema

-- alternatively, use the Snowflake Scripting approach shown here

-- Parse and extract all PDFs on a stage after filtering to the desired documents
DECLARE
    file_cursor CURSOR FOR
        SELECT RELATIVE_PATH
        FROM DIRECTORY(@ADE_APPS_DB.FDA.DOCS)
        WHERE SIZE < 1000000  -- Files smaller than 1MB (1,000,000 bytes)
            AND RELATIVE_PATH LIKE 'devices/P%.pdf'  -- Filter based on file names within directory
        LIMIT 10;
    current_file_path STRING;
    full_stage_path STRING;
    
    parse_ret OBJECT;
    extract_ret OBJECT;

BEGIN
    FOR file_record IN file_cursor DO
        current_file_path := file_record.RELATIVE_PATH;

        full_stage_path := '@"ADE_APPS_DB"."FDA"."DOCS"/' || :current_file_path;
             
        -- Parse document (capture the return OBJECT)
        CALL api.parse(
            file_path => :full_stage_path,
            model => 'dpt-2-latest',
            output_table => 'medical_device_parse' -- Name of your output table for parse. It will be created for you.
        ) INTO :parse_ret;
        
         -- Extract using the parse return object
        CALL api.extract(
            parse_result => :parse_ret,
            output_table => 'medical_device_extract', -- Name of your output table for extract. It will be created for you.
            model => 'extract-latest',
            schema => '{
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


SELECT * FROM DB.MEDICAL_DEVICE_PARSE;

SELECT * FROM DB.MEDICAL_DEVICE_EXTRACT;


-- copy parse and extract results to final location

CREATE OR REPLACE TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_PARSE AS
SELECT DISTINCT *
FROM ADE.DB.MEDICAL_DEVICE_PARSE;

CREATE OR REPLACE TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACT AS
SELECT DISTINCT *
FROM ADE.DB.MEDICAL_DEVICE_EXTRACT;

-- inspect new table
SELECT * FROM ADE.DB.MEDICAL_DEVICE_PARSE;

-- inspect new table
SELECT * FROM ADE.DB.MEDICAL_DEVICE_EXTRACT;


-- create a structured table based on the extracted entities/contents
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

-- inspect new table
SELECT * FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_EXTRACTED;


-- create a table to prepare for cortex search based on the parsed chunks
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

-- inspect new table
SELECT * FROM ADE_APPS_DB.FDA.MEDICAL_DEVICE_CHUNKS;



-- enable change tracking on the table
ALTER TABLE ADE_APPS_DB.FDA.MEDICAL_DEVICE_CHUNKS
SET CHANGE_TRACKING = TRUE;

-- create cortex search service (you can also create via the UI: ai & ml -> cortex search)
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

-- test query
-- what this does: Searches the indexed chunk text and returns the top 10 most relevant chunks for "intended use of the medical device"
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


-- this was created via the Cortex Analyst UI. Easily configure this by navigating to AI & ML -> Cortex Analyst.  
-- A semantic view is a Cortex Analyst–friendly layer on top of one or more Snowflake tables.

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


USE DATABASE ADE_APPS_DB;
USE SCHEMA ADE_APPS_DB.FDA;

-- create stored procedure to generate presigned urls for files in stages
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

-- create the agent and define the toolset
-- easily configure this by navigating to ai & ml -> cortex analyst / agents

CREATE OR REPLACE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.LANDINGAI_ADE_MEDICAL_DEVICE
WITH PROFILE = '{ "display_name": "LandingAI ADE Medical Device Agent" }'
COMMENT = $$ Interact with FDA medical device safety and effectiveness summaries which exist in a Snowflake stage and have been parsed with Agentic Document Extraction. $$
FROM SPECIFICATION $$
{
  "models": { "orchestration": "auto" },
  "instructions": {
    "response": "You are a helpful assistant that can answer questions about FDA medical devices that we have in our database and analyze research using PubMed.",
    "orchestration": "When the user asks about FDA medical devices, first query the database using the medical device lookup. When the user asks for supporting source text or document evidence, use the fda_document_search tool to retrieve relevant chunks. When presenting supporting chunks, deduplicate results by CHUNK_ID. Do not cite the same CHUNK_ID more than once. Prefer table and figure chunks (CHUNK_TYPE='table' and CHUNK_TYPE='figure') if they contain relevent information. If the user asks to open the original PDF, use the Dynamic_Doc_URL_Tool to generate a temporary URL. "
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
      "max_results": 8,
      "name": "ADE_APPS_DB.FDA.FDA_DOCUMENT_SEARCH",
      "title_column": "RELATIVE_PATH"
    },
    "medical_device_lookup": {
      "execution_environment": { "query_timeout": 300, "type": "warehouse", "warehouse": "WH_LANDINGAI_ADE" },
      "semantic_view": "ADE_APPS_DB.FDA.MEDICAL_DEVICES"
    }
  }
}
$$;


-- test; entire Cortex Search pipeline is working end-to-end
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


-- test; returns a URL string you can open in a browser.
CALL ADE_APPS_DB.FDA.GET_FILE_PRESIGNED_URL_SP('devices/P160048S021B.pdf', 60);


-- we used account admin here, so make sure to provide necessary permissions to the roles that will run the agent, including usage on the database, schema, staage, read on the tables and services, including Cortex Search, Cortex, and Agents

-- from here users can navigate to ai.snowflake.com to interact with the agent
-- go try it