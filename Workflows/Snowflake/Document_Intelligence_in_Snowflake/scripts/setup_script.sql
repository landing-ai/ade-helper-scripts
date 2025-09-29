-- script will create the necessary snowflake objects
use role accountadmin;

-- create snowflake objects
create database if not exists landingai_apps_db;
create schema  if not exists landingai_apps_db.fda;
create stage if not exists landingai_apps_db.fda.docs
    directory = (enable = true);

create warehouse wh_landingai_ade if not exists
    with warehouse_size = 'XSMALL'
    auto_suspend = 300
    auto_resume = TRUE;
    
use database landingai_apps_db;
use schema landingai_apps_db.fda;
create stage if not exists LANDINGAI_APPS_DB.FDA.SEMANTIC_MODELS; 

-- enable cross region cortex
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';
USE "LANDINGAI_AGENTIC_DOCUMENT_EXTRACTION";


-------------------------------------------------------------------
-- grant LandingAI app access to fda docs

GRANT USAGE ON DATABASE LANDINGAI_APPS_DB TO APPLICATION "LANDINGAI_AGENTIC_DOCUMENT_EXTRACTION";
GRANT USAGE ON SCHEMA LANDINGAI_APPS_DB.FDA TO APPLICATION "LANDINGAI_AGENTIC_DOCUMENT_EXTRACTION";
GRANT READ, WRITE ON STAGE LANDINGAI_APPS_DB.FDA.DOCS TO APPLICATION "LANDINGAI_AGENTIC_DOCUMENT_EXTRACTION";

-- put your files in the /devices stage subfolder to align with the rest of this flow
ls @landingai_apps_db.fda.docs;

-- create the table to land extracted document contents
create table if not exists landingai_apps_db.fda.medical_device_docs (
    relative_path varchar,
    file_contents variant,
    stage_name varchar,
    last_modified timestamp_tz
)
;

-- batch processing from directory table to perform parsing + extraction
-- the schema is passed to pull out specific content from each document which is used to insert into structured table
insert into landingai_apps_db.fda.medical_device_docs (relative_path, file_contents, stage_name, last_modified)
    -- pull from directory table
    with stage_files as (
            select *
            from directory ('@landingai_apps_db.fda.docs')
        )
            
        select
            f.relative_path as relative_path,
            doc_extraction.snowflake_extract_doc_structure(
                '@landingai_apps_db.fda.docs/' || f.relative_path,
                    '
        {
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
              "description": "Executive summary: what the device does, who it’s for, key results, and benefit–risk conclusion"
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
        }

        '    
            ) as file_contents,
            'landingai_apps_db.fda.docs' as stage_name,
            last_modified
        from stage_files f
;

-- create a structured table based on the extracted entities/contents
create or replace table landingai_apps_db.fda.medical_device_extracted as (
    select
        file_contents:data.extracted_schema:applicant_address::STRING AS applicant_address,
        file_contents:data.extracted_schema:applicant_name::STRING AS applicant_name,
        file_contents:data.extracted_schema:application_type::STRING AS application_type,
        try_to_date(file_contents:data.extracted_schema:approval_date::STRING) AS approval_date,
        file_contents:data.extracted_schema:device_generic_name::STRING AS device_generic_name,
        file_contents:data.extracted_schema:device_trade_name::STRING AS device_trade_name,
        file_contents:data.extracted_schema:indications_for_use::STRING AS indications_for_use,
        file_contents:data.extracted_schema:key_outcomes_summary::STRING AS key_outcomes_summary,
        file_contents:data.extracted_schema:overall_summary::STRING AS overall_summary,
        file_contents:data.extracted_schema:premarket_approval_number::STRING AS premarket_approval_number
    from landingai_apps_db.fda.medical_device_docs

    )
;

-- Create a table to prepare for Cortex Search based on the parsed chunks
create or replace table landingai_apps_db.fda.medical_device_chunks as (
    select 
        relative_path,
        row_number() over (partition by file_contents order by chunk_index.index) - 1 as chunk_index,
        chunk_index.value AS chunk_info,
        chunk_index.value:chunk_id::STRING as chunk_id,
        grounding_index.value:page::INTEGER as page_number,
        chunk_index.value:chunk_type::STRING as chunk_type,
        chunk_index.value:grounding::VARIANT as chunk_grounding,
        chunk_index.value:text::STRING as chunk_text,
        stage_name,
        stage_name || '/' || relative_path as full_path,
         BUILD_STAGE_FILE_URL('@landingai_apps_db.fda.docs', relative_path) as file_url
    from landingai_apps_db.fda.medical_device_docs,
    lateral flatten(input => file_contents:data.chunks) as chunk_index,
    lateral flatten(input => chunk_index.value:grounding) as grounding_index
)
;

-- enable change tracking on the table
alter table landingai_apps_db.fda.medical_device_chunks set CHANGE_TRACKING = TRUE;
-- create cortex search service - This can also be created via the UI at AI & ML -> Cortex Search
create or replace cortex search service landingai_apps_db.fda.FDA_DOCUMENT_SEARCH
	on CHUNK_TEXT
	attributes RELATIVE_PATH,FULL_PATH
	warehouse='WH_LANDING_ADE'
	target_lag='1 day' -- adjust to what is necessary for business
	as (
	SELECT
		CHUNK_TEXT,RELATIVE_PATH,FULL_PATH,CHUNK_INDEX,CHUNK_INFO,CHUNK_ID,PAGE_NUMBER,CHUNK_TYPE,CHUNK_GROUNDING,STAGE_NAME
	FROM LANDINGAI_APPS_DB.FDA.MEDICAL_DEVICE_CHUNKS
);


-- this was created via the Cortex Analyst UI. Easily configure this by navigating to AI & ML -> Cortex Analyst
create or replace semantic view LANDINGAI_APPS_DB.FDA.MEDICAL_DEVICES
	tables (
		MEDICAL_DEVICE_EXTRACTED
	)
	dimensions (
		MEDICAL_DEVICE_EXTRACTED.APPLICANT_ADDRESS as APPLICANT_ADDRESS with synonyms=('applicant_location','company_address','business_address','organization_location','registrant_address','submitter_address','manufacturer_address') comment='The street address of the applicant, including the company name, street number, city, state, and zip code.',
		MEDICAL_DEVICE_EXTRACTED.APPLICANT_NAME as APPLICANT_NAME with synonyms=('applicant','applicant_full_name','applicant_title','company_name','organization_name','submitter_name','registrant_name','manufacturer_name') comment='The name of the company or organization that submitted the medical device for approval or clearance.',
		MEDICAL_DEVICE_EXTRACTED.APPLICATION_TYPE as APPLICATION_TYPE with synonyms=('application_category','submission_type','filing_classification','request_format','application_classification','submission_category','filing_type') comment='The type of application submitted to the FDA for approval of a medical device, where PMA (Premarket Approval) is for new devices and PMA SUPPLEMENT is for modifications to an existing approved device.',
		MEDICAL_DEVICE_EXTRACTED.APPROVAL_DATE as APPROVAL_DATE with synonyms=('approval_timestamp','certification_date','clearance_date','date_approved','date_cleared','date_certified','authorized_date','verified_date') comment='The date on which the medical device was approved for use.',
		MEDICAL_DEVICE_EXTRACTED.DEVICE_GENERIC_NAME as DEVICE_GENERIC_NAME with synonyms=('generic_device_name','device_common_name','nonproprietary_name','device_identifier','common_device_name','device_description') comment='The DEVICE_GENERIC_NAME column contains the generic name of a medical device, which is a general term that describes the device''s function or purpose, and is often used to categorize or group similar devices together.',
		MEDICAL_DEVICE_EXTRACTED.DEVICE_TRADE_NAME as DEVICE_TRADE_NAME with synonyms=('brand_name','product_name','device_brand','trade_name','product_title','commercial_name','proprietary_name') comment='The name of the medical device as it is commercially known or branded.',
		MEDICAL_DEVICE_EXTRACTED.INDICATIONS_FOR_USE as INDICATIONS_FOR_USE with synonyms=('intended_use','purpose','intended_purpose','indications','usage_indications','intended_applications','medical_indications','device_indications','use_indications') comment='This column contains the indications for use for various medical devices, including their intended purposes, target patient populations, and any relevant contraindications or warnings.',
		MEDICAL_DEVICE_EXTRACTED.KEY_OUTCOMES_SUMMARY as KEY_OUTCOMES_SUMMARY with synonyms=('key_findings','main_results','summary_of_key_results','key_trial_outcomes','major_outcomes','trial_summary','key_study_results','main_study_findings') comment='This column contains summaries of key outcomes from clinical trials and studies for various medical devices, including survival rates, adverse event rates, and effectiveness endpoints, providing an overview of the devices'' performance and safety.',
		MEDICAL_DEVICE_EXTRACTED.OVERALL_SUMMARY as OVERALL_SUMMARY with synonyms=('general_summary','summary_overview','overall_description','brief_summary','summary_report','executive_summary') comment='This column contains a detailed summary of the medical device, including its intended use, clinical trial results, benefits, and risks, providing a comprehensive overview of the device''s safety and effectiveness.',
		MEDICAL_DEVICE_EXTRACTED.PREMARKET_APPROVAL_NUMBER as PREMARKET_APPROVAL_NUMBER with synonyms=('premarket_approval_code','pma_number','premarket_approval_id','premarket_clearance_number','fda_approval_number','premarket_authorization_number') comment='Unique identifier assigned by the FDA to a medical device that has been approved for marketing through the premarket approval (PMA) process.'
	)
	comment='This semantic view captures key information about medical devices submitting premarket approval applications to the FDA.'
	with extension (CA='{"tables":[{"name":"MEDICAL_DEVICE_EXTRACTED","dimensions":[{"name":"APPLICANT_ADDRESS","sample_values":["Quest Diagnostics Nichols Institute, 33608 Ortega Highway, San Juan Capistrano, CA 92675","CVRx, Inc.\\n9201 West Broadway Avenue, Suite 650\\nMinneapolis, Minnesota 55445","200 Valleywood, Suite B100, The Woodlands, Texas 77380"]},{"name":"APPLICANT_NAME","sample_values":["Quest Diagnostics Nichols Institute","CVRx, Inc.","Berlin Heart Inc."]},{"name":"APPLICATION_TYPE","sample_values":["PMA","PMA_SUPPLEMENT"]},{"name":"DEVICE_GENERIC_NAME","sample_values":["Stimulator, Carotid Sinus","Enzyme-linked immunosorbent in vitro diagnostic assay for the semi-quantitative detection of antibodies (IgG) to AAVrh74 capsid in human serum","Ventricular Assist Device (VAD)"]},{"name":"DEVICE_TRADE_NAME","sample_values":["BAROSTIM NEO\\u00000 System","EXCOR\\u0000ae Pediatric Ventricular Assist Device","Quest Diagnostics AAVrh74 Antibody ELISA CDx"]},{"name":"INDICATIONS_FOR_USE","sample_values":["The Eversense\\u0000ae E3 CGM System is intended for continually measuring glucose levels in adults (18 years and older) with diabetes for up to 180 days. The system is indicated for use to replace fingerstick blood glucose measurements for diabetes treatment decisions. The system is intended to: Provide real-time glucose readings; Provide glucose trend information; Provide alerts for the detection and prediction of episodes of low blood glucose (hypoglycemia) and high blood glucose (hyperglycemia). The system is a prescription device. Historical data from the system can be interpreted to aid in providing therapy adjustments. These adjustments should be based on patterns and trends seen over time. The system is intended for single patient use.","The BAROSTIM NEO\\u00000 System is indicated for the improvement of symptoms of heart failure \\u0013 quality of life, six-minute hall walk and functional status, for patients who remain symptomatic despite treatment with guideline-directed medical therapy, are NYHA Class III or Class II (who had a recent history of Class III), have a left ventricular ejection fraction \\u0013 35%, a NT-proBNP < 1600 pg/ml and excluding patients indicated for Cardiac Resynchronization Therapy (CRT) according to AHA/ACC/ESC guidelines.","The Quest Diagnostics AAVrh74 Antibody ELISA CDx is an enzyme-linked immunosorbent in vitro diagnostic assay intended for the semi-quantitative detection of antibodies (IgG) to AAVrh74 capsid in human serum. The test reports an antibody titer, and a semi-quantitative interpretation of the test results derived from the antibody titer. Patients with an AAVrh74 antibody titer <1:400 are reported as not elevated for AAVrh74 antibody titers and may be eligible for treatment with the gene therapy. Patients with an AAVrh74 antibody titer \\u001E1:400 are reported as elevated for AAVrh74 antibody titers and are ineligible for treatment with the gene therapy. The test is for prescription use only. The test is intended to be used in conjunction with other available clinical information as an aid to identify patients eligible for treatment with indicated gene therapies."]},{"name":"KEY_OUTCOMES_SUMMARY","sample_values":["In the pivotal IDE trial, survival to transplant or successful recovery was 87.5% in Cohort 1 and 91.7% in Cohort 2, both significantly higher than matched ECMO controls (70.8% and 60.4%, respectively). Serious adverse event (SAE) rates were 0.068 and 0.079 events per patient-day for Cohorts 1 and 2, well below the performance goal of 0.25. In the full implant population (n=565), 73.3% were successfully transplanted or weaned, 21.8% died, and 15.6% experienced ischemic or hemorrhagic stroke. The majority of patients (64%) survived to successful weaning or transplantation with no neurologic adverse events. Major adverse events included major bleeding, infection, and neurological dysfunction.","The Quest Diagnostics AAVrh74 Antibody ELISA CDx demonstrated high concordance with clinical trial assays in two bridging studies: Bridging Study 1 showed a positive percent agreement (PPA) of 92.5%, negative percent agreement (NPA) of 90.2%, and overall percent agreement (OPA) of 91.5%. Bridging Study 2 showed a PPA of 94.1%, NPA of 100%, and OPA of 99.3%. Analytical validation studies demonstrated the device met all acceptance criteria for accuracy, specificity, sensitivity, precision, stability, linearity, high-dose hook effect, carry over, and cross-contamination. The main risks are false positive or false negative results, but these have been minimized through robust controls and mitigations.","In the pivotal BeAT-HF trial, the BAROSTIM NEO System demonstrated a 96.8% MANCE-free rate at 6 months (lower bound 95% CI: 92.8%), meeting the primary safety endpoint. Effectiveness endpoints at 6 months showed a statistically significant improvement in six-minute walk distance (mean difference +60.1 meters, p<0.001), quality of life (mean difference -14.1 points, p<0.001), and a significant reduction in NT-proBNP in the combined cohort (-24.6%, p=0.004) compared to medical management alone. NYHA class improved by at least one class in 65% of device patients versus 31% of controls. No deaths or unanticipated adverse events were reported."]},{"name":"OVERALL_SUMMARY","sample_values":["The EXCOR\\u0000ae Pediatric Ventricular Assist Device is an extracorporeal, pneumatically driven, pulsatile VAD intended as a bridge to cardiac transplantation for pediatric patients with severe isolated left ventricular or biventricular dysfunction. It is the only FDA-approved option for small pediatric patients (<1.2 m\\u0000b2 BSA) requiring long-term mechanical circulatory support. Clinical studies demonstrated that the device provides effective support, with 73% of patients surviving to transplant or successful weaning, and a majority experiencing no neurologic adverse events. The main risks are major bleeding, infection, and neurological dysfunction (stroke rate ~15.6% in all-comers, ~30% in pivotal studies), but these are considered acceptable given the lack of alternatives and the high risk of death without support. The benefit-risk profile is favorable, with the device providing a life-saving option for a vulnerable population with no other effective treatments.","The BAROSTIM NEO System is an implantable device for electrical stimulation of the carotid sinus baroreceptors, intended to improve symptoms of heart failure in patients with NYHA Class III or II (recent Class III), LVEF \\u0013 35%, and NT-proBNP < 1600 pg/ml, who remain symptomatic despite guideline-directed medical therapy and are not candidates for CRT. In the pivotal BeAT-HF trial, the device demonstrated significant improvements in functional capacity (six-minute walk distance), quality of life, and NT-proBNP compared to medical management alone, with a high safety profile (96.8% MANCE-free at 6 months, no deaths or unanticipated adverse events). The benefit-risk assessment supports that the probable benefits outweigh the probable risks for the indicated population.","The Quest Diagnostics AAVrh74 Antibody ELISA CDx is a companion diagnostic device for the semi-quantitative detection of antibodies (IgG) to AAVrh74 capsid in human serum, used to aid in identifying patients with Duchenne Muscular Dystrophy (DMD) eligible for treatment with ELEVIDYS gene therapy. The device is intended for prescription use and is to be used in conjunction with other clinical information. Analytical and clinical bridging studies demonstrated high accuracy, specificity, sensitivity, and precision, with strong concordance to clinical trial assays. The main benefit is to ensure only eligible patients receive gene therapy, minimizing unnecessary exposure and maximizing therapeutic benefit. Risks of false positive or negative results are minimized by robust controls. The device met all performance acceptance criteria, and its use does not alter the benefit-risk profile of the associated gene therapy. FDA concluded that the probable benefits outweigh the risks, supporting approval."]},{"name":"PREMARKET_APPROVAL_NUMBER","sample_values":["P160035","P250002","P180050"]}],"time_dimensions":[{"name":"APPROVAL_DATE","sample_values":["2017-06-06","2025-07-24","2019-08-16"]}]}],"verified_queries":[{"name":"What is the most recent device approved in the data?","question":"What is the most recent device approved in the data?","sql":"SELECT\\n  device_trade_name,\\n  device_generic_name,\\n  applicant_name,\\n  approval_date\\nFROM\\n  medical_device_extracted\\nORDER BY\\n  approval_date DESC NULLS LAST\\nLIMIT\\n  1","use_as_onboarding_question":false,"verified_by":"Snowflwake User","verified_at":1756332942}]}');
;


use database landingai_apps_db;
use schema landingai_apps_db.fda;

-- Create stored procedure to generate presigned URLs for files in internal stages
CREATE OR REPLACE PROCEDURE Get_File_Presigned_URL_SP(
    RELATIVE_FILE_PATH STRING, 
    EXPIRATION_MINS INTEGER DEFAULT 60
)
RETURNS STRING
LANGUAGE SQL
COMMENT = 'Generates a presigned URL for a file in the static @INTERNAL_DATA_STAGE. Input is the relative file path.'
EXECUTE AS CALLER
AS
$$
DECLARE
    presigned_url STRING;
    sql_stmt STRING;
    expiration_seconds INTEGER;
    stage_name STRING DEFAULT '@landingai_apps_db.fda.docs';
BEGIN
    expiration_seconds := EXPIRATION_MINS * 60;

    sql_stmt := 'SELECT GET_PRESIGNED_URL(' || stage_name || ', ' || '''' || RELATIVE_FILE_PATH || '''' || ', ' || expiration_seconds || ') AS url';
    
    EXECUTE IMMEDIATE :sql_stmt;
    
    
    SELECT "URL"
    INTO :presigned_url
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
    
    RETURN :presigned_url;
END;
$$;

--'This tools uses the ID Column coming from Cortex Search tools for reference docs and returns a temp URL for users to view & download the docs.\n\nReturned URL should be presented as a HTML Hyperlink where doc title should be the text and out of this tool should be the url.\n\nURL format for PDF docs that are are like this which has no PDF in the url. Create the Hyperlink format so the PDF doc opens up in a browser instead of downloading the file.\nhttps://domain/path/unique_guid'


-- keep in mind access requirements here: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents#access-control-requirements

-- Easily configure this by navigating to AI & ML -> Cortex Analyst
CREATE OR REPLACE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.LANDINGAI_ADE_MEDICAL_DEVICE
WITH PROFILE='{ "display_name": "LandingAI ADE Medical Device Agent" }'
    COMMENT=$$ Enables users to interact with medical device safety and effectiveness summaries, including extracted contents and full document contents in addition to PumMed research articles. $$
FROM SPECIFICATION $$
{"models":{"orchestration":"auto"},"instructions":{"response":"You are a helpful assistant that can answer questions about FDA medical devices that we have in our database and analyze research using pubmed.","orchestration":"When the user asks about documents, make sure to check the database first using the medical device lookup and filter results in our FDA Document search Cortex Search service for that specific device.\n"},"tools":[{"tool_spec":{"type":"cortex_analyst_text_to_sql","name":"medical_device_lookup","description":"TABLE1:\n- Database: LANDINGAI_APPS_DB, Schema: FDA\n- This table contains information about medical devices that have submitted premarket approval applications to the FDA. It captures detailed data about device specifications, applicant information, clinical outcomes, and regulatory approval details.\n- The table serves as a central repository for tracking medical device approvals, providing insights into device performance, safety profiles, and regulatory compliance across different manufacturers and device types.\n- LIST OF COLUMNS: APPLICANT_ADDRESS (street address of the applicant including company details), APPLICANT_NAME (company or organization name that submitted the device), APPLICATION_TYPE (type of FDA application - PMA or PMA_SUPPLEMENT), DEVICE_GENERIC_NAME (generic functional name of the medical device), DEVICE_TRADE_NAME (commercial brand name of the device), INDICATIONS_FOR_USE (intended medical purposes and target patient populations), KEY_OUTCOMES_SUMMARY (clinical trial results and effectiveness data), OVERALL_SUMMARY (comprehensive device overview including benefits and risks), PREMARKET_APPROVAL_NUMBER (unique FDA identifier for approved devices), APPROVAL_DATE (date when device was approved by FDA)\n\nREASONING:\nThis semantic view focuses on FDA medical device premarket approvals, providing a comprehensive dataset for analyzing regulatory approval patterns, device safety and effectiveness, and manufacturer performance. The single table structure contains all necessary information to understand the complete lifecycle of medical device approvals, from application submission through clinical outcomes and final regulatory decision. The data enables analysis of approval trends, device categories, clinical performance metrics, and regulatory compliance across different manufacturers and time periods.\n\nDESCRIPTION:\nThe MEDICAL_DEVICES semantic view provides comprehensive information about medical devices that have undergone FDA premarket approval processes, stored in the LANDINGAI_APPS_DB.FDA schema. This view captures detailed regulatory data including device specifications, manufacturer information, clinical trial outcomes, and approval timelines for both new device applications (PMA) and modifications to existing devices (PMA_SUPPLEMENT). The dataset enables analysis of medical device approval patterns, safety and effectiveness profiles, and regulatory compliance trends across different manufacturers and device categories. Users can explore relationships between device types, clinical outcomes, approval dates, and manufacturer performance to gain insights into the medical device regulatory landscape."}},{"tool_spec":{"type":"cortex_search","name":"PUBMED_BIOMEDICAL_RESEARCH_CORPUS","description":"Biomedical research conducted by PubMed which can be used to answer questions related to biomedical research."}},{"tool_spec":{"type":"cortex_search","name":"fda_document_search","description":"Looks up medical device approval documents containing the full contents submitted by companies for FDA approval"}},{"tool_spec":{"type":"generic","name":"Dynamic_Doc_URL_Tool","description":"'This tools uses the ID Column coming from Cortex Search tools for reference docs and returns a temp URL for users to view & download the docs.\\n\\nReturned URL should be presented as a HTML Hyperlink where doc title should be the text and out of this tool should be the url.\\n\\nURL format for PDF docs that are are like this which has no PDF in the url. Create the Hyperlink format so the PDF doc opens up in a browser instead of downloading the file.\\nhttps://domain/path/unique_guid'\n\n","input_schema":{"type":"object","properties":{"expiration_mins":{"description":"the expiration in minutes","type":"number"},"relative_file_path":{"description":"'This tools uses the ID Column coming from Cortex Search tools for reference docs and returns a temp URL for users to view & download the docs.\\n\\nReturned URL should be presented as a HTML Hyperlink where doc title should be the text and out of this tool should be the url.\\n\\nURL format for PDF docs that are are like this which has no PDF in the url. Create the Hyperlink format so the PDF doc opens up in a browser instead of downloading the file.\\nhttps://domain/path/unique_guid'\n","type":"string"}},"required":["expiration_mins","relative_file_path"]}}}],"tool_resources":{"Dynamic_Doc_URL_Tool":{"execution_environment":{"query_timeout":274,"type":"warehouse","warehouse":"WH_LANDINGAI_ADE"},"identifier":"LANDINGAI_APPS_DB.FDA.GET_FILE_PRESIGNED_URL_SP","name":"GET_FILE_PRESIGNED_URL_SP(VARCHAR, DEFAULT NUMBER)","type":"procedure"},"PUBMED_BIOMEDICAL_RESEARCH_CORPUS":{"id_column":"ARTICLE_URL","max_results":4,"name":"PUBMED_BIOMEDICAL_RESEARCH_CORPUS.OA_COMM.PUBMED_OA_CKE_SEARCH_SERVICE","title_column":"ARTICLE_CITATION"},"fda_document_search":{"id_column":"FULL_PATH","max_results":4,"name":"LANDINGAI_APPS_DB.FDA.FDA_DOCUMENT_SEARCH","title_column":"RELATIVE_PATH"},"medical_device_lookup":{"execution_environment":{"query_timeout":300,"type":"warehouse","warehouse":"WH_LANDINGAI_ADE"},"semantic_view":"LANDINGAI_APPS_DB.FDA.MEDICAL_DEVICES"}}}
$$;

-- we used account admin here, so make sure to provide necessary permissions to the roles that will run the agent, including usage on the database, schema, staage, read on the tables and services, including Cortex Search, Cortex, and Agents
-- from here users can navigate to ai.snowflake.com to interact with the agent