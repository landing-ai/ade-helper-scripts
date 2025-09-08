-- ========================
-- SETUP: ROLE + SCHEMA
-- ========================

USE ROLE ACCOUNTADMIN; -- Ensure you have sufficient privileges
USE DATABASE DEMOS_ADE_FINANCE;
USE SCHEMA INVOICES;

-- ========================
-- 1. STAGES
-- ========================

-- [STAGE 1] Long-term archival stage for processed files.
-- Auto-compression is OFF in the pipeline; files are readable.
-- This stage is *never purged*. Use for audit and traceability.
CREATE OR REPLACE STAGE DEMOS_ADE_FINANCE.INVOICES.PARSED_INVOICES_COMPLETED
  DIRECTORY = (ENABLE = TRUE);  -- enables LIST @stage

-- [STAGE 2] Temporary ingest buffer.
-- Used by the pipeline for mini-batch loads.
-- Files here are deleted (PURGE) after a successful COPY.
CREATE STAGE IF NOT EXISTS INGEST_TMP;

-- ========================
-- 2. FILE FORMATS
-- ========================

-- Standard CSV format for main/line data
CREATE FILE FORMAT IF NOT EXISTS CSV_STD
  TYPE = CSV
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  SKIP_HEADER = 1
  NULL_IF = ('', 'NULL')
  EMPTY_FIELD_AS_NULL = TRUE;

-- JSON format for structured fields (e.g. markdown, chunk output)
CREATE FILE FORMAT IF NOT EXISTS JSON_STD
  TYPE = JSON
  STRIP_OUTER_ARRAY = FALSE;

-- ========================
-- 3. PIPELINE TABLES
-- ========================

-- Table 1 of 4: Full Markdown output for each document
-- Used for inspection, QA, and visual JSON grounding
CREATE OR REPLACE TABLE DEMOS_ADE_FINANCE.INVOICES.MARKDOWN (
  RUN_ID                  STRING,
  INVOICE_UUID            VARCHAR NOT NULL,
  DOCUMENT_NAME           VARCHAR,
  SENT_AT                 TIMESTAMP_TZ,
  AGENTIC_DOC_VERSION     VARCHAR,
  MARKDOWN                VARIANT, --This will hold the parsing output for all pages of the document

  CONSTRAINT PK_MARKDOWN PRIMARY KEY (INVOICE_UUID)
);


-- Table 2 of 4: Individual parsed chunks (text spans with metadata)
-- Often used for debugging, LLM groundings or RAG applications
CREATE OR REPLACE TABLE DEMOS_ADE_FINANCE.INVOICES.PARSED_CHUNKS (
    RUN_ID          STRING,
    INVOICE_UUID    VARCHAR NOT NULL,
    DOCUMENT_NAME   STRING,
    chunk_id        STRING,
    chunk_type      STRING,
    text            STRING,
    page            NUMBER,
    box_l           FLOAT,
    box_t           FLOAT,
    box_r           FLOAT,
    box_b           FLOAT,

    CONSTRAINT PK_PARSED_CHUNKS PRIMARY KEY (CHUNK_ID)
);

-- Table 3 of 4: Main invoice-level fields (1 row per invoice)
CREATE OR REPLACE TABLE DEMOS_ADE_FINANCE.INVOICES.INVOICES_MAIN (
  RUN_ID                  STRING,
  INVOICE_UUID            VARCHAR NOT NULL,
  DOCUMENT_NAME           VARCHAR,
  SENT_AT                 TIMESTAMP_TZ,
  AGENTIC_DOC_VERSION     VARCHAR,

  -- DocumentInfo
  INVOICE_DATE_RAW        VARCHAR,
  INVOICE_DATE            DATE,
  INVOICE_NUMBER          VARCHAR,
  ORDER_DATE              VARCHAR,
  PO_NUMBER               VARCHAR,
  STATUS                  VARCHAR,
  
  -- CustomerInfo
  SOLD_TO_NAME            VARCHAR,
  SOLD_TO_ADDRESS         VARCHAR,
  CUSTOMER_EMAIL          VARCHAR,

  -- SupplierInfo
  SUPPLIER_NAME           VARCHAR,
  SUPPLIER_ADDRESS        VARCHAR,
  REPRESENTATIVE          VARCHAR,
  EMAIL                   VARCHAR,
  PHONE                   VARCHAR,
  GSTIN                   VARCHAR,
  PAN                     VARCHAR,

   -- Terms and shipping details
  PAYMENT_TERMS           VARCHAR,
  SHIP_VIA                VARCHAR,
  SHIP_DATE               VARCHAR,
  TRACKING_NUMBER         VARCHAR,

  -- Financial summary
  CURRENCY                VARCHAR,
  TOTAL_DUE_RAW           VARCHAR,   

  TOTAL_DUE               NUMBER(18,4),
  SUBTOTAL                NUMBER(18,4),
  TAX                     NUMBER(18,4),
  SHIPPING                NUMBER(18,4),
  HANDLING_FEE            NUMBER(18,4),

  -- Metadata about extractions
  SUPPLIER_NAME_REF       STRING,
  SUPPLIER_NAME_CONF      FLOAT,
  TOTAL_DUE_RAW_REF       STRING,
  TOTAL_DUE_RAW_CONF      FLOAT,
 
  CONSTRAINT PK_INVOICES_MAIN PRIMARY KEY (INVOICE_UUID)
);

-- Table 4 of 4: Extracted line item rows (1+ per invoice)
CREATE OR REPLACE TABLE DEMOS_ADE_FINANCE.INVOICES.INVOICE_LINE_ITEMS (
  RUN_ID                  STRING,
  INVOICE_UUID            VARCHAR NOT NULL,        -- FK to invoices_main (logical)
  DOCUMENT_NAME           VARCHAR,
  SENT_AT                 TIMESTAMP_TZ,
  AGENTIC_DOC_VERSION     VARCHAR,

  LINE_INDEX              NUMBER(9,0),             -- 0-based index

  LINE_NUMBER             VARCHAR,
  SKU                     VARCHAR,
  DESCRIPTION             VARCHAR,
  QUANTITY                FLOAT,
  UNIT_PRICE              NUMBER(18,4),
  PRICE                   NUMBER(18,4),
  AMOUNT                  NUMBER(18,4),
  TOTAL                   NUMBER(18,4)
);

-- ========================
-- 4. ROLES & GRANTS
-- ========================

-- Create dedicated pipeline role
CREATE ROLE IF NOT EXISTS ADE_DEMOS;

-- Grant to pipeline user
GRANT ROLE ADE_DEMOS TO USER MACHINE_USER_2;

-- Warehouse usage (for compute)
GRANT USAGE ON WAREHOUSE SNOWFLAKE_TUTORIALS TO ROLE ADE_DEMOS;

-- Schema + database visibility
GRANT USAGE ON DATABASE DEMOS_ADE_FINANCE TO ROLE ADE_DEMOS;
GRANT USAGE ON SCHEMA DEMOS_ADE_FINANCE.INVOICES TO ROLE ADE_DEMOS;

-- Table-level access
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA DEMOS_ADE_FINANCE.INVOICES TO ROLE ADE_DEMOS;
GRANT SELECT, INSERT, UPDATE, DELETE ON FUTURE TABLES IN SCHEMA DEMOS_ADE_FINANCE.INVOICES TO ROLE ADE_DEMOS;

-- Stages: allow read/write to input/output buffers
GRANT READ, WRITE ON STAGE DEMOS_ADE_FINANCE.INVOICES.PARSED_INVOICES_COMPLETED TO ROLE ADE_DEMOS; 
GRANT READ, WRITE ON STAGE DEMOS_ADE_FINANCE.INVOICES.INGEST_TMP TO ROLE ADE_DEMOS; 

-- File formats: needed for pipeline COPY
GRANT CREATE STAGE, CREATE FILE FORMAT ON SCHEMA DEMOS_ADE_FINANCE.INVOICES TO ROLE ADE_DEMOS;
GRANT USAGE ON FILE FORMAT DEMOS_ADE_FINANCE.INVOICES.CSV_STD  TO ROLE ADE_DEMOS;
GRANT USAGE ON FILE FORMAT DEMOS_ADE_FINANCE.INVOICES.JSON_STD TO ROLE ADE_DEMOS;

