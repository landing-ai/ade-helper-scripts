"""
ADE Lambda Handler
==================
Serverless document processing using LandingAI's ADE API.
Processes documents from S3 using the ADE S3 connector.

Processing Modes:
    1. Chunk-based parsing (default) - Returns text, tables, figures, marginalia
    2. Schema-based extraction - Uses Pydantic models to extract specific fields

API Documentation: https://docs.landing.ai/ade
Author: Ava Xia
"""

# Standard library imports
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# AWS SDK imports
import boto3

# LandingAI ADE imports
from agentic_doc.parse import parse
from agentic_doc.connectors import S3ConnectorConfig

# ===========================
# Configuration
# ===========================

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants
HANDLER_VERSION = "1.1.0"
MAX_PAGES_FOR_EXTRACTION = 50

# Environment variables
VISION_AGENT_API_KEY = os.environ.get('VISION_AGENT_API_KEY')
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'cf-mle-testing')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-2')

# ===========================
# Extraction Schema Registry
# ===========================

# Dictionary to store available extraction schemas
EXTRACTION_SCHEMAS: Dict[str, Any] = {}

# Load extraction schemas from config module
try:
    from config import SCHEMAS
    EXTRACTION_SCHEMAS = SCHEMAS
    logger.info(f"✅ Loaded extraction schemas: {list(EXTRACTION_SCHEMAS.keys())}")
except ImportError as e:
    logger.warning(f"⚠️ Could not import schemas from config: {e}")
    logger.info("📋 No extraction schemas loaded - using chunk-based parsing only")

# Log initialization
logger.info("="*60)
logger.info(f"🚀 Handler version: {HANDLER_VERSION}")
if EXTRACTION_SCHEMAS:
    logger.info(f"📊 Available extraction schemas: {list(EXTRACTION_SCHEMAS.keys())}")
else:
    logger.info("📋 No extraction schemas loaded - using chunk-based parsing only")
logger.info("="*60)

# ===========================
# Utility Functions
# ===========================

def serialize_parsed_document(doc: Any, add_statistics: bool = True) -> Dict[str, Any]:
    """
    Convert ParsedDocument to dict and add statistics.
    
    Args:
        doc: ParsedDocument from parse() function
        add_statistics: Whether to add chunk statistics
        
    Returns:
        Serialized document dictionary with optional statistics
    """
    # Since agentic-doc uses Pydantic models, we can use built-in serialization
    # Try Pydantic v2 first, then v1
    try:
        # Pydantic v2
        if hasattr(doc, 'model_dump'):
            serialized = doc.model_dump(mode='json')
        # Pydantic v1
        elif hasattr(doc, 'dict'):
            serialized = doc.dict()
        else:
            # Fallback to manual serialization if needed
            raise AttributeError("No Pydantic serialization method found")
    except Exception as e:
        logger.warning(f"Pydantic serialization failed: {e}, using manual serialization")
        # Manual fallback for older versions or edge cases
        serialized = {
            "markdown": doc.markdown,
            "chunks": [],
            "doc_type": getattr(doc, 'doc_type', 'unknown'),
            "start_page_idx": getattr(doc, 'start_page_idx', None),
            "end_page_idx": getattr(doc, 'end_page_idx', None)
        }
        
        # Manually serialize chunks if needed
        for chunk in doc.chunks:
            chunk_dict = {
                "text": chunk.text,
                "chunk_type": str(chunk.chunk_type),  # Convert enum to string
                "chunk_id": str(chunk.chunk_id),
                "grounding": []
            }
            if hasattr(chunk, 'grounding') and chunk.grounding:
                for ground in chunk.grounding:
                    chunk_dict["grounding"].append({
                        "page": ground.page,
                        "box": {"l": ground.box.l, "t": ground.box.t, "r": ground.box.r, "b": ground.box.b}
                    })
            serialized["chunks"].append(chunk_dict)
    
    # Optionally add statistics (custom addition, not in original model)
    if add_statistics and "chunks" in serialized and serialized["chunks"]:
        chunk_type_counts = {}
        max_page = 0
        
        for chunk in serialized["chunks"]:
            # Count chunk types
            chunk_type = chunk.get("chunk_type", "unknown")
            chunk_type_counts[chunk_type] = chunk_type_counts.get(chunk_type, 0) + 1
            
            # Track max page
            if "grounding" in chunk:
                for ground in chunk["grounding"]:
                    page = ground.get("page", 0)
                    if page > max_page:
                        max_page = page
        
        # Add metadata if not present
        if "metadata" not in serialized:
            serialized["metadata"] = {}
            
        serialized["metadata"]["statistics"] = {
            "total_chunks": len(serialized["chunks"]),
            "chunk_types": chunk_type_counts,
            "total_pages": max_page + 1 if max_page > 0 else 1
        }
    
    return serialized

# ===========================
# Main Lambda Handler
# ===========================

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for ADE document processing from S3.
    
    Args:
        event: Lambda event containing S3 trigger or manual parameters
        context: Lambda context object
        
    Returns:
        Response dictionary with status code and processing results
        
    Event parameters for manual invocation:
        - bucket_name: S3 bucket name
        - prefix: S3 prefix to process (optional)
        - pattern: File pattern filter (optional, e.g., "*.pdf")
        - document_type: Schema type for extraction (optional)
        - use_extraction: Enable extraction mode (optional)
    """

    try:
        # Log handler start
        logger.info("="*60)
        logger.info(f"🚀 Handler version {HANDLER_VERSION} started")
        logger.info(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
        # Check if this is an S3 event trigger
        specific_file = None
        trigger_type = "manual"

        if event.get("Records") and event["Records"][0].get("s3"):
            # S3 trigger - process ONLY the specific file that was uploaded
            s3_record = event["Records"][0]["s3"]
            bucket_name = s3_record["bucket"]["name"]
            specific_file = s3_record["object"]["key"]
            prefix = None
            trigger_type = "s3_event"
            logger.info(f"📄 S3 trigger: Processing single file {specific_file}")
        else:
            # Manual invocation - process folder/prefix
            bucket_name = event.get("bucket_name", os.environ.get("BUCKET_NAME"))
            prefix = event.get("prefix")
            
            # Check if prefix is actually a single file (ends with common file extensions)
            if prefix and any(prefix.endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.docx']):
                specific_file = prefix
                prefix = None
                logger.info(f"📄 Manual invocation: Processing single file {specific_file}")
            else:
                logger.info(f"🔧 Manual invocation: Processing prefix {prefix or 'all'}")

        if not bucket_name:
            raise ValueError("No bucket_name provided")

        # Configure S3 connector
        config = S3ConnectorConfig(
            bucket_name=bucket_name,
            region_name=os.environ.get("AWS_REGION", "us-east-2")
        )

        # Parse documents
        # Note: ADE's parse() supports additional parameters:
        # - result_save_dir: Auto-save JSON (adds result_path to ParsedDocument)
        # - grounding_save_dir: Save visual grounding images
        # - connector_pattern: Filter files by pattern (e.g., "*.pdf")
        # - extraction_schema: Extract specific structured data
        # - include_marginalia: Include headers/footers (default: True)
        # We use minimal parameters for Lambda efficiency
        
        # Get optional parameters from event
        file_pattern = event.get("pattern")  # e.g., "*.pdf", "*.png"
        document_type = event.get("document_type")  # e.g., "invoice"
        use_extraction = event.get("use_extraction", False)  # Flag to use extraction model
        
        # Handle string boolean values
        if isinstance(use_extraction, str):
            use_extraction = use_extraction.lower() in ['true', '1', 'yes']
        
        # Log processing mode for debugging
        logger.info(f"📋 Processing mode: use_extraction={use_extraction}, document_type={document_type}")
        
        # Build parse parameters for agentic-doc library
        # When using S3Connector, first parameter is 'documents' (S3ConnectorConfig)
        parse_kwargs = {"documents": config}
        
        if specific_file:
            parse_kwargs["connector_path"] = specific_file
        elif prefix:
            parse_kwargs["connector_path"] = prefix
            
        if file_pattern:
            parse_kwargs["connector_pattern"] = file_pattern
            logger.info(f"🔍 Processing files matching pattern: {file_pattern}")
        
        # Check if we should use extraction model
        if use_extraction or document_type:
            if document_type in EXTRACTION_SCHEMAS:
                # Use the appropriate schema for extraction
                schema_class = EXTRACTION_SCHEMAS[document_type]
                parse_kwargs["extraction_model"] = schema_class
                logger.info(f"✨ Using {schema_class.__name__} for '{document_type}' extraction")
            elif document_type:
                available = list(EXTRACTION_SCHEMAS.keys()) if EXTRACTION_SCHEMAS else []
                logger.warning(f"⚠️  Document type '{document_type}' not available. Available types: {available}")
        
        # Parse documents with configured parameters
        results = parse(**parse_kwargs)

        logger.info(f"✅ Successfully parsed {len(results)} documents")
        
        # If processing from a prefix, get list of actual files processed
        # This helps map results to original filenames
        processed_files = []
        if prefix and not specific_file:
            s3_client = boto3.client('s3')
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
            
            for page in pages:
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Filter by pattern if specified
                    if file_pattern:
                        import fnmatch
                        if fnmatch.fnmatch(key, file_pattern):
                            processed_files.append(key)
                    elif key.endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.docx')):
                        processed_files.append(key)
            
            logger.info(f"📁 Found {len(processed_files)} files matching criteria")

        # Convert results to JSON-serializable format
        serialized_results = []
        
        for i, doc in enumerate(results):
            # Determine document name - try multiple attributes
            doc_name = "unknown"
            
            # First try to get from ParsedDocument attributes
            if hasattr(doc, 'name'):
                doc_name = doc.name
            elif hasattr(doc, 'file_name'):
                doc_name = doc.file_name
            elif hasattr(doc, 'document_name'):
                doc_name = doc.document_name
            elif hasattr(doc, 'path'):
                doc_name = doc.path
            elif hasattr(doc, 'source'):
                doc_name = doc.source
            
            # If still no name and we have a list of processed files, use that
            if doc_name == "unknown" and i < len(processed_files):
                doc_name = processed_files[i]
            elif doc_name == "unknown" and specific_file:
                # If processing single file, use that name
                doc_name = specific_file
            
            # Clean up the name - get just filename if it's a path
            if '/' in doc_name:
                doc_name = doc_name.split('/')[-1]
            
            # Final fallback
            if doc_name == "unknown":
                doc_name = f"doc_{i+1}"
            
            logger.info(f"   📄 Processing document {i+1}/{len(results)}: {doc_name}")
            
            # Check if this document has extraction results (from using extraction_model)
            if hasattr(doc, 'extraction') and doc.extraction:
                # Document was parsed with extraction_model
                extraction_data = doc.extraction
                
                # Convert Pydantic model to dict with proper JSON serialization
                if hasattr(extraction_data, 'model_dump'):
                    # Pydantic v2 - use mode='json' to ensure JSON-serializable output
                    extraction_dict = extraction_data.model_dump(mode='json')
                elif hasattr(extraction_data, 'dict'):
                    # Pydantic v1 - dates are automatically converted to strings
                    extraction_dict = extraction_data.dict()
                else:
                    extraction_dict = extraction_data
                
                # Create serialized result with extraction data
                serialized_results.append({
                    "type": "extracted",
                    "document_type": document_type if document_type else "unknown",
                    "extraction": extraction_dict,
                    "markdown": getattr(doc, 'markdown', ''),
                    "doc_type": getattr(doc, 'doc_type', 'unknown'),
                    "metadata": {
                        "document_name": doc_name,
                        "pages": getattr(doc, 'end_page_idx', 1) if hasattr(doc, 'end_page_idx') else 1,
                        "extraction_model": schema_class.__name__ if 'schema_class' in locals() else "unknown"
                    }
                })
                
                # Log extraction summary (customize based on your schema)
                if document_type == 'invoice' and 'line_items' in extraction_dict:
                    logger.info(f"      ✅ Extracted invoice with {len(extraction_dict.get('line_items', []))} line items")
                else:
                    logger.info(f"      ✅ Extracted {document_type} successfully")
            else:
                # Regular parsing without extraction - returns chunks
                result = serialize_parsed_document(doc)
                # Add document name to metadata if not present
                if 'metadata' not in result:
                    result['metadata'] = {}
                result['metadata']['document_name'] = doc_name
                serialized_results.append(result)

        # Save results to S3
        s3_client = boto3.client('s3')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if specific_file:
            # For single file, save with related name
            # Extract just the filename without path
            file_name = specific_file.split('/')[-1].rsplit('.', 1)[0]  # Remove path and extension
            # Determine if extraction or parsing mode
            if use_extraction or document_type:
                mode_suffix = "extracted"
            else:
                mode_suffix = "parsed"
            result_key = f"ade-results/{file_name}_{mode_suffix}_{timestamp}.json"
        else:
            # For batch processing
            if use_extraction or document_type:
                result_key = f"ade-results/batch_extracted_{timestamp}.json"
            else:
                result_key = f"ade-results/batch_parsed_{timestamp}.json"

        result_data = {
            "processed_at": timestamp,
            "trigger_type": trigger_type,
            "bucket": bucket_name,
            "prefix": prefix,
            "specific_file": specific_file,
            "parsed_count": len(results),
            "documents": serialized_results
        }

        s3_client.put_object(
            Bucket=bucket_name,
            Key=result_key,
            Body=json.dumps(result_data, indent=2),
            ContentType='application/json'
        )

        logger.info(f"💾 Saved results to s3://{bucket_name}/{result_key}")
        
        # Log completion
        logger.info("="*60)
        logger.info(f"✅ Processing complete")
        if specific_file:
            logger.info(f"📄 File: {specific_file}")
        else:
            logger.info(f"📊 Documents: {len(results)}")
        logger.info(f"📍 Results: s3://{bucket_name}/{result_key}")
        logger.info("="*60)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "ok": True,
                "parsed_count": len(results),
                "result_location": f"s3://{bucket_name}/{result_key}"
            })
        }

    except ValueError as e:
        # Configuration or input errors
        logger.error("="*60)
        logger.error(f"❌ Configuration error: {e}")
        logger.error("="*60)
        return {
            "statusCode": 400,
            "body": json.dumps({
                "ok": False,
                "error": str(e),
                "error_type": "configuration_error"
            })
        }
    
    except ImportError as e:
        # Missing dependencies
        logger.error("="*60)
        logger.error(f"❌ Import error: {e}")
        logger.error("💡 Make sure 'agentic-doc' is installed in the Lambda container")
        logger.error("="*60)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "ok": False,
                "error": "Missing required dependencies",
                "details": str(e),
                "error_type": "import_error"
            })
        }
    
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error("="*60)
        logger.error("❌ ADE S3 parse failed with unexpected error")
        logger.exception("Stack trace:")
        error_message = str(e)
        
        # Check for specific error patterns and provide helpful guidance
        if "VISION_AGENT_API_KEY" in error_message:
            logger.error("🔑 API key issue detected")
            logger.error("💡 Set VISION_AGENT_API_KEY environment variable")
            logger.error("="*60)
            return {
                "statusCode": 401,
                "body": json.dumps({
                    "ok": False,
                    "error": "API key issue detected",
                    "help": "Check VISION_AGENT_API_KEY environment variable",
                    "error_type": "authentication_error"
                })
            }
        elif "402 Payment Required" in error_message:
            logger.error("💰 API quota exceeded")
            logger.error("💡 Check your LandingAI account credits at https://app.landing.ai/")
            logger.error("="*60)
        elif "exceeds the maximum of 50 pages" in error_message:
            logger.error(f"📄 Document exceeds {MAX_PAGES_FOR_EXTRACTION}-page limit")
            logger.error("💡 Use parse mode instead or split the document")
            logger.error("="*60)
        else:
            logger.error("="*60)
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "ok": False,
                "error": error_message,
                "error_type": "unexpected_error"
            })
        }
