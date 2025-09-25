"""
Unified Utility Functions for ADE Lambda S3 Processing
========================================================
Combines all utility functions for AWS setup, S3 operations, Lambda management,
document processing, and monitoring.
"""

import os
import json
import time
import boto3
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ===========================
# AWS Setup Functions
# ===========================

def setup_aws_environment() -> Tuple[Dict, Dict, str, Any]:
    """
    Initialize AWS environment with configuration from Settings.
    
    Returns:
        Tuple of (config_dict, clients_dict, aws_account_id, session)
    """
    # Load settings from .env or environment
    from config import get_settings
    settings = get_settings()
    
    # Create session with profile if specified
    # IMPORTANT: Force our settings region, not the profile's default
    if settings.aws_profile and settings.aws_profile != "default":
        session = boto3.Session(
            profile_name=settings.aws_profile,
            region_name=settings.aws_region  # Force our region from .env
        )
    else:
        session = boto3.Session(region_name=settings.aws_region)
    
    # Ensure the region is correctly set
    session._session.set_config_variable('region', settings.aws_region)
    
    # Initialize clients with forced region
    # Create config with extended timeout for Lambda client
    lambda_config = Config(
        read_timeout=900,  # 15 minutes (max Lambda timeout)
        connect_timeout=60,
        retries={'max_attempts': 0},
        region_name=settings.aws_region  # Force region in config
    )
    
    # Force region for all clients
    clients = {
        's3': session.client('s3', region_name=settings.aws_region),
        'lambda': session.client('lambda', region_name=settings.aws_region, config=lambda_config),
        'ecr': session.client('ecr', region_name=settings.aws_region),
        'iam': session.client('iam', region_name=settings.aws_region),
        'logs': session.client('logs', region_name=settings.aws_region)
    }
    
    # Get account ID and verify credentials
    try:
        sts = session.client('sts', region_name=settings.aws_region)
        identity = sts.get_caller_identity()
        account_id = identity['Account']
        
        print(f"✅ AWS Environment configured")
        print(f"   Profile: {settings.aws_profile}")
        print(f"   Region: {settings.aws_region}")  # Use settings region instead of session
        # Mask account ID for security
        masked_account = account_id[:4] + "X" * (len(account_id) - 8) + account_id[-4:] if len(account_id) > 8 else "XXXXXXXXXXXX"
        print(f"   Account: {masked_account}")
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code in ['ExpiredToken', 'TokenRefreshRequired', 'UnrecognizedClientException']:
            print("⚠️  AWS credentials expired or invalid!")
            print(f"   Profile: {settings.aws_profile}")
            print("\n🔄 To refresh credentials:")
            print(f"   1. Run: aws sso login --profile {settings.aws_profile}")
            print(f"   2. Re-run this cell")
            account_id = 'EXPIRED'
        else:
            print(f"❌ AWS credential error: {e}")
            account_id = 'ERROR'
    except Exception as e:
        print(f"⚠️  Could not verify AWS credentials: {e}")
        account_id = settings.aws_account_id or 'unknown'
    
    # Return settings dict for compatibility
    config_dict = settings.dict()
    return config_dict, clients, account_id, session

# Alias for backward compatibility
get_aws_clients = setup_aws_environment

# ===========================
# S3 Operations
# ===========================

def list_s3_files(s3_client, bucket_name: str, prefix: str = "", max_files: int = 100) -> List[Dict]:
    """List files in S3 bucket with metadata."""
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=max_files
        )
        
        files = []
        for obj in response.get('Contents', []):
            files.append({
                'File': obj['Key'],
                'Size': f"{obj['Size']/1024:.1f} KB",
                'Modified': obj['LastModified'].strftime('%Y-%m-%d %H:%M')
            })
        
        print(f"📂 Files in s3://{bucket_name}/{prefix}")
        print(f"Found {len(files)} files")
        return files
        
    except Exception as e:
        print(f"❌ Error listing S3 files: {e}")
        return []

def setup_s3_trigger(s3_client, lambda_client, bucket_name: str, function_name: str, 
                     folder: str = "invoices/") -> bool:
    """Configure S3 event trigger for Lambda."""
    try:
        # Check bucket region
        bucket_location = s3_client.get_bucket_location(Bucket=bucket_name)
        bucket_region = bucket_location.get('LocationConstraint', 'us-east-1')
        # us-east-1 returns None as LocationConstraint
        if bucket_region is None:
            bucket_region = 'us-east-1'
            
        # Get Lambda function ARN and region
        response = lambda_client.get_function(FunctionName=function_name)
        function_arn = response['Configuration']['FunctionArn']
        function_region = function_arn.split(':')[3]
        
        # Check region compatibility
        if bucket_region != function_region:
            print(f"⚠️  Region mismatch detected!")
            print(f"   S3 Bucket region: {bucket_region}")
            print(f"   Lambda function region: {function_region}")
            print(f"\n❌ S3 event notifications require the bucket and Lambda function to be in the same region.")
            print(f"\n💡 Solutions:")
            print(f"   1. Deploy Lambda in {bucket_region} region, OR")
            print(f"   2. Create a new S3 bucket in {function_region} region")
            return False
        
        # Add S3 permission to Lambda
        statement_id = f"s3-trigger-{folder.replace('/', '-')}"
        
        try:
            lambda_client.add_permission(
                FunctionName=function_name,
                StatementId=statement_id,
                Action='lambda:InvokeFunction',
                Principal='s3.amazonaws.com',
                SourceArn=f'arn:aws:s3:::{bucket_name}/*'
            )
            print("✅ Added S3 permission to Lambda")
        except lambda_client.exceptions.ResourceConflictException:
            print("ℹ️  S3 permission already exists")
        
        # Configure S3 bucket notification
        notification_config = {
            'LambdaFunctionConfigurations': [
                {
                    'Id': f'ProcessDocuments-{folder}',
                    'LambdaFunctionArn': function_arn,
                    'Events': ['s3:ObjectCreated:*'],
                    'Filter': {
                        'Key': {
                            'FilterRules': [
                                {'Name': 'prefix', 'Value': folder},
                                {'Name': 'suffix', 'Value': '.pdf'}
                            ]
                        }
                    }
                }
            ]
        }
        
        s3_client.put_bucket_notification_configuration(
            Bucket=bucket_name,
            NotificationConfiguration=notification_config
        )
        
        print("✅ S3 trigger configured!")
        print(f"   📤 Upload PDFs to: s3://{bucket_name}/{folder}")
        print(f"   ⚡ They will auto-process with Lambda")
        return True
        
    except Exception as e:
        print(f"❌ Error setting up S3 trigger: {e}")
        return False

# ===========================
# Lambda Management
# ===========================

def check_lambda_environment(lambda_client, function_name: str) -> Dict:
    """Check Lambda function environment configuration."""
    try:
        response = lambda_client.get_function_configuration(FunctionName=function_name)
        env_vars = response.get('Environment', {}).get('Variables', {})
        
        print("🔐 Lambda Environment Configuration")
        print("="*50)
        print("Environment Variables:")
        
        # Check critical environment variables
        api_key = env_vars.get('VISION_AGENT_API_KEY', '')
        bucket = env_vars.get('BUCKET_NAME', '')
        region = env_vars.get('AWS_REGION', '')
        
        if api_key:
            print(f"   ✅ 🔑 LandingAI API Key: {api_key[:4]}****{api_key[-4:]}")
        else:
            print("   ❌ 🔑 LandingAI API Key: Not set")
            
        if bucket:
            print(f"   ✅ 🪣 S3 Bucket: {bucket}")
        else:
            print("   ❌ 🪣 S3 Bucket: Not set")
            
        if region:
            print(f"   ✅ 🌍 AWS Region: {region}")
        else:
            print("   ℹ️  🌍 AWS Region: Using default")
        
        return {
            'configured': bool(api_key and bucket),
            'env_vars': env_vars
        }
        
    except Exception as e:
        print(f"❌ Error checking Lambda environment: {e}")
        return {'configured': False}

def get_lambda_metrics(lambda_client, function_name: str) -> Dict:
    """Get Lambda function metrics and configuration."""
    try:
        response = lambda_client.get_function_configuration(FunctionName=function_name)
        
        print("📊 Lambda Function Metrics")
        print("="*50)
        print(f"   Function: {response['FunctionName']}")
        print(f"   State: {response['State']}")
        print(f"   Memory: {response['MemorySize']} MB")
        print(f"   Timeout: {response['Timeout']} seconds")
        print(f"   Architecture: {response.get('Architectures', ['x86_64'])[0]}")
        print(f"   Package Type: {response.get('PackageType', 'Zip')}")
        print(f"   Last Modified: {response['LastModified']}")
        
        return response
        
    except Exception as e:
        print(f"❌ Error getting Lambda metrics: {e}")
        return {}

# ===========================
# Document Processing
# ===========================

def process_single_file(lambda_client, function_name: str, bucket_name: str,
                        file_key: str, extraction: bool = False,
                        document_type: Optional[str] = None, verbose: bool = False) -> Optional[Dict]:
    """Process a single file with Lambda."""
    mode = "extraction" if extraction else "parsing"
    if verbose:
        print(f"📄 Processing single file ({mode} mode)")
        print(f"   File: {file_key}")
    
    payload = {
        "bucket_name": bucket_name,
        "prefix": file_key
    }
    
    if extraction:
        payload["use_extraction"] = True
        # Always provide document_type for extraction, default to invoice
        if not document_type:
            document_type = "invoice"
        payload["document_type"] = document_type
    elif document_type:
        # If document_type is provided without extraction flag, enable extraction
        payload["use_extraction"] = True
        payload["document_type"] = document_type
    
    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        body = json.loads(result.get('body', '{}'))
        
        if body.get('ok'):
            if verbose:
                print(f"✅ Success!")
                print(f"   Documents: {body.get('parsed_count', 0)}")
                print(f"   Results: {body.get('result_location', 'N/A')}")
            
            # If extraction mode and result location exists, fetch the actual extraction data
            if extraction and body.get('result_location'):
                s3_path = body['result_location']
                if s3_path.startswith('s3://'):
                    # Parse S3 path
                    parts = s3_path.replace('s3://', '').split('/', 1)
                    if len(parts) == 2:
                        result_bucket, result_key = parts
                        try:
                            # Create S3 client if not available
                            s3_client = boto3.client('s3')
                            response = s3_client.get_object(Bucket=result_bucket, Key=result_key)
                            extraction_content = json.loads(response['Body'].read())
                            
                            # Add extraction data to response
                            if extraction_content and 'documents' in extraction_content:
                                # Get first document's extraction if single file
                                docs = extraction_content['documents']
                                if docs and len(docs) > 0 and docs[0].get('extraction'):
                                    body['extraction'] = docs[0]['extraction']
                            elif isinstance(extraction_content, list) and extraction_content:
                                # Handle list format
                                if extraction_content[0].get('extraction'):
                                    body['extraction'] = extraction_content[0]['extraction']
                        except Exception as e:
                            if verbose:
                                print(f"   ⚠️  Could not fetch extraction data: {e}")
            
            return body
        else:
            if verbose:
                print(f"❌ Error: {body.get('error', 'Unknown')}")
            return None
    except Exception as e:
        if verbose:
            print(f"❌ Failed: {e}")
        return None

def process_batch_extraction(lambda_client, s3_client, function_name: str,
                            bucket_name: str, prefix: str,
                            document_type: str = "invoice",
                            extraction: bool = True, session=None) -> Optional[pd.DataFrame]:
    """Process batch documents and return DataFrame with results."""
    print(f"📋 Batch {document_type.title()} {'Extraction' if extraction else 'Parsing'} Test")
    print("="*80)
    
    # Count files
    response = s3_client.list_objects_v2(
        Bucket=bucket_name,
        Prefix=prefix,
        MaxKeys=100
    )
    
    files = [obj for obj in response.get('Contents', []) if obj['Key'].endswith('.pdf')]
    file_count = len(files)
    
    if file_count == 0:
        print("❌ No PDF files found")
        return None
    
    print(f"   Found {file_count} PDF files to process")
    
    # Estimate time
    estimated_time = file_count * 10  # ~10 seconds per file
    if estimated_time > 60:
        print(f"   ⏱️  Estimated time: {estimated_time//60}-{(estimated_time//60)+1} minutes")
    
    # Invoke Lambda
    print("\n🚀 Invoking Lambda for batch processing...")
    start_time = time.time()
    
    payload = {
        "bucket_name": bucket_name,
        "prefix": prefix,
        "document_type": document_type,
        "use_extraction": extraction,
        "pattern": "*.pdf"
    }
    
    # Show progress bar during Lambda invocation
    import threading
    import sys
    
    # Flag to stop the progress bar
    stop_progress = False
    
    def show_progress():
        """Show animated progress bar while waiting for Lambda."""
        chars = ['⣾', '⣷', '⣯', '⣟', '⡿', '⢿', '⣻', '⣽']
        idx = 0
        start = time.time()
        while not stop_progress:
            elapsed = time.time() - start
            mins, secs = divmod(int(elapsed), 60)
            time_str = f"{mins:02d}:{secs:02d}"
            
            # Calculate estimated progress based on file count
            estimated_total = file_count * 10  # 10 seconds per file estimate
            progress_pct = min(100, int((elapsed / estimated_total) * 100))
            
            # Create progress bar
            bar_width = 30
            filled = int(bar_width * progress_pct / 100)
            bar = '█' * filled + '░' * (bar_width - filled)
            
            sys.stdout.write(f'\r   {chars[idx % len(chars)]} Processing: [{bar}] {progress_pct}% - {time_str}')
            sys.stdout.flush()
            time.sleep(0.1)
            idx += 1
        
        # Clear the progress line
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        sys.stdout.flush()
    
    # Start progress bar in background thread
    progress_thread = threading.Thread(target=show_progress)
    progress_thread.daemon = True
    progress_thread.start()
    
    # Invoke Lambda with the already-configured client
    try:
        # The lambda_client already has extended timeout from get_aws_clients()
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Stop progress bar
        stop_progress = True
        progress_thread.join(timeout=0.5)
        
        elapsed = time.time() - start_time
        print(f"⏱️  Lambda returned after {elapsed:.1f} seconds")
        
        # Parse response
        result = json.loads(response['Payload'].read())
        body = json.loads(result.get('body', '{}'))
        
        if not body.get('ok'):
            print(f"❌ Processing failed: {body.get('error', 'Unknown error')}")
            return None
        
        result_location = body.get('result_location', '')
        parsed_count = body.get('parsed_count', 0)
        
        print(f"\n✅ Batch processing successful!")
        print(f"   Documents processed: {parsed_count}")
        if parsed_count > 0:
            print(f"   Average time per document: {elapsed/parsed_count:.1f}s")
        print(f"   Results location: {result_location}")
        print()
        
        # Download and parse results
        print("📥 Downloading results from S3...")
        result_key = result_location.replace(f"s3://{bucket_name}/", "")
        obj = s3_client.get_object(Bucket=bucket_name, Key=result_key)
        data = json.loads(obj['Body'].read())
        
        
        # Convert to DataFrame
        if extraction and document_type == "invoice":
            return extract_invoice_dataframe(data)
        else:
            return parse_results_dataframe(data)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def extract_invoice_dataframe(data: Dict) -> pd.DataFrame:
    """Extract invoice data into a pandas DataFrame."""
    # Check if data itself is the extraction result (not wrapped in documents)
    if 'invoice_info' in data or 'customer_info' in data:
        # Single document extraction result
        documents = [data]
    else:
        documents = data.get('documents', [])
    
    rows = []
    
    # Debug: Show what we received
    if not documents:
        print(f"   Debug: No documents found in data. Keys: {list(data.keys())}")
        return pd.DataFrame()
    
    print(f"   Processing {len(documents)} documents...")
    
    for i, doc in enumerate(documents):
        try:
                
            # Skip None documents
            if doc is None:
                continue
                
            # Ensure doc is a dictionary
            if not isinstance(doc, dict):
                continue
            
            # Try different structures - check extraction_output first (new format), then extraction (old format)
            ext = None
            if 'extraction_output' in doc:
                ext = doc['extraction_output']
            elif 'extraction' in doc:
                ext = doc['extraction']
                # Skip if extraction is None (parsing was done but no extraction)
                if ext is None:
                    continue
            elif 'invoice_info' in doc or 'customer_info' in doc:
                # If no extraction key found, maybe the document itself is the extraction
                ext = doc
            
            # If we found extraction data, process it
            if ext:
                # Get document name - handle if doc is a string or other type
                if isinstance(doc, dict):
                    doc_name = doc.get('metadata', {}).get('document_name', f'doc_{i+1}')
                else:
                    doc_name = f'doc_{i+1}'
                
                if '/' in doc_name:
                    doc_name = doc_name.split('/')[-1]
                
                # Extract fields - safely handle None
                invoice_info = ext.get('invoice_info', {}) if ext else {}
                customer_info = ext.get('customer_info', {}) if ext else {}
                company_info = ext.get('company_info', {}) if ext else {}
                totals = ext.get('totals_summary', {}) if ext else {}
                
                rows.append({
                    'File': doc_name,
                    'Invoice #': invoice_info.get('invoice_number', '-'),
                    'Date': invoice_info.get('invoice_date', '-'),
                    'Customer': customer_info.get('sold_to_name', '-'),
                    'Supplier': company_info.get('supplier_name', '-'),
                    'Subtotal': totals.get('subtotal', 0),
                    'Tax': totals.get('tax', 0),
                    'Total': totals.get('total_due', 0),
                    'Currency': totals.get('currency', 'USD'),
                    'Line Items': len(ext.get('line_items', [])) if ext else 0,
                    'Status': invoice_info.get('status', 'N/A')
                })
        except Exception as e:
            print(f"   Error processing document {i}: {str(e)}")
    
    if not rows:
        print(f"   Warning: No extracted data found in {len(documents)} documents")
    
    df = pd.DataFrame(rows)
    
    # Format currency columns only if they exist
    for col in ['Subtotal', 'Tax', 'Total']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"${x:,.2f}" if pd.notna(x) and x != 0 else "-")
    
    return df

def parse_results_dataframe(data: Dict) -> pd.DataFrame:
    """Convert parsing results into a pandas DataFrame."""
    documents = data.get('documents', [])
    rows = []
    
    for i, doc in enumerate(documents):
        doc_name = doc.get('metadata', {}).get('document_name', f'doc_{i+1}')
        if '/' in doc_name:
            doc_name = doc_name.split('/')[-1]
            
        rows.append({
            'File': doc_name,
            'Type': doc.get('doc_type', 'unknown'),
            'Pages': doc.get('metadata', {}).get('statistics', {}).get('total_pages', 1),
            'Chunks': doc.get('metadata', {}).get('statistics', {}).get('total_chunks', 0),
            'Tables': doc.get('metadata', {}).get('statistics', {}).get('chunk_types', {}).get('table', 0),
            'Figures': doc.get('metadata', {}).get('statistics', {}).get('chunk_types', {}).get('figure', 0)
        })
    
    return pd.DataFrame(rows)

# ===========================
# Monitoring Functions
# ===========================

def get_lambda_invocation_stats(logs_client, function_name: str, hours_back: int = 24) -> Dict:
    """Get Lambda invocation statistics from CloudWatch logs."""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours_back)
        
        response = logs_client.filter_log_events(
            logGroupName=f'/aws/lambda/{function_name}',
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern='REPORT'
        )
        
        total = len(response.get('events', []))
        
        print(f"📊 Lambda Invocation Statistics (last {hours_back} hours)")
        print("="*50)
        print(f"   Total Invocations: {total}")
        
        return {
            'total_invocations': total,
            'success_rate': 100 if total > 0 else 0
        }
        
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        return {}

def get_error_logs(logs_client, function_name: str, hours_back: int = 24) -> List[str]:
    """Get error logs from Lambda function."""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours_back)
        
        response = logs_client.filter_log_events(
            logGroupName=f'/aws/lambda/{function_name}',
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern='ERROR'
        )
        
        errors = response.get('events', [])
        
        print(f"❌ Error Logs (last {hours_back} hours)")
        print("="*50)
        
        if errors:
            for error in errors[:5]:  # Show first 5
                print(f"   • {error['message']}")
        else:
            print("✅ No errors found")
        
        return errors
        
    except Exception as e:
        print(f"❌ Error getting logs: {e}")
        return []

# ===========================
# Display Utility Functions
# ===========================

def display_parsing_result(result: Dict, file_name: str = "", s3_client=None) -> None:
    """
    Display parsing results in a clean, formatted way.
    
    Args:
        result: The result from process_single_file with extraction=False
        file_name: Name of the file being processed
        s3_client: Optional pre-authenticated S3 client
    """
    from IPython.display import display, JSON
    
    if file_name:
        print(f"📄 Parsing document: {file_name}")
    print("="*60)
    print("Mode: Parsing (document structure)")
    print("Returns: List of chunks (text, table, figure types)")
    print("="*60)
    
    if result and (result.get('success') or result.get('ok')):
        # Check if we have S3 results location or result_location
        s3_location = result.get('results_location') or result.get('result_location')
        if s3_location:
            print(f"\n✅ Parsing successful!")
            print(f"   Results saved to: {s3_location}")
            
            # Try to download and display results if s3_client available
            try:
                # Use provided s3_client or create new one
                if s3_client is None:
                    import boto3
                    # Check if AWS profile is set
                    aws_profile = os.getenv('AWS_PROFILE')
                    if aws_profile:
                        session = boto3.Session(profile_name=aws_profile)
                        s3 = session.client('s3')
                    else:
                        s3 = boto3.client('s3')
                else:
                    s3 = s3_client
                
                # Parse S3 path
                s3_path = s3_location.replace('s3://', '')
                bucket = s3_path.split('/')[0]
                key = '/'.join(s3_path.split('/')[1:])
                
                # Download the results and display them
                response = s3.get_object(Bucket=bucket, Key=key)
                parsed_data = json.loads(response['Body'].read())
                
                # Display the parsed document
                display_parsed_document(parsed_data)
                    
            except Exception as e:
                print(f"\n   Note: Could not fetch results from S3 for display")
                print(f"   Results are available at: {s3_location}")
        
        # Handle documents in the result directly
        elif 'documents' in result:
            documents = result.get('documents', [])
            if documents and len(documents) > 0:
                print("✅ Processing completed")
            else:
                print("✅ Processing completed but no documents returned")
        else:
            print("✅ Processing completed")
            print(f"   Result keys: {list(result.keys())}")
    else:
        print("❌ Parsing failed. Check Lambda logs for details.")

def display_parsed_document(parsed_data) -> None:
    """
    Helper function to display a parsed document's structure.
    Handles list of chunks with chunk_type (text, table, figure).
    """
    from IPython.display import display, JSON
    
    # Handle list of chunks (actual ADE parse output structure)
    if isinstance(parsed_data, list):
        # Count chunk types
        text_chunks = [c for c in parsed_data if c.get('chunk_type') == 'text']
        table_chunks = [c for c in parsed_data if c.get('chunk_type') == 'table']
        figure_chunks = [c for c in parsed_data if c.get('chunk_type') == 'figure']
        
        print(f"\n📋 Document Structure Summary:")
        print(f"   Total Chunks: {len(parsed_data)}")
        print(f"   Text Chunks: {len(text_chunks)}")
        print(f"   Tables: {len(table_chunks)}")
        print(f"   Figures: {len(figure_chunks)}")
        
        # Show first few text chunks
        if text_chunks:
            print(f"\n📝 First 3 Text Chunks:")
            print("-"*40)
            for i, chunk in enumerate(text_chunks[:3], 1):
                text = chunk.get('text', '')[:150]
                if len(chunk.get('text', '')) > 150:
                    text += "..."
                print(f"   Chunk {i}: {text}")
        
        # Show table information
        if table_chunks:
            print(f"\n📊 Tables Detected:")
            for i, table in enumerate(table_chunks[:3], 1):
                # Tables have a different structure - they contain rows of data
                rows = table.get('rows', [])
                print(f"   Table {i}: {len(rows)} rows")
        
        # Show figure information  
        if figure_chunks:
            print(f"\n🖼️ Figures Detected: {len(figure_chunks)}")
        
        # Display full parsed data in JSON format
        print("\n🔍 Full Parsed Data (JSON):")
        print("-"*60)
        display(JSON(parsed_data))
    else:
        # Fallback if structure is different
        print("\n📄 Raw Parsed Output:")
        display(JSON(parsed_data))

def display_extraction_result(result: Dict, file_name: str = "", document_type: str = "invoice", s3_client=None) -> None:
    """
    Display extraction results in a clean, formatted way.
    
    Args:
        result: The result from process_single_file with extraction=True
        file_name: Name of the file being processed
        document_type: Type of document (invoice, purchase_order, receipt)
        s3_client: Optional pre-authenticated S3 client
    """
    from IPython.display import display, JSON
    
    if file_name:
        print(f"📄 Extracting structured data from: {file_name}")
    print("="*60)
    print("Mode: Extraction (structured data)")
    print(f"Schema: {document_type.title()}ExtractionSchema")
    print("="*60)
    
    if result and (result.get('success') or result.get('ok')):
        # Check if we have S3 results location or result_location
        s3_location = result.get('results_location') or result.get('result_location')
        if s3_location:
            print(f"\n✅ Extraction successful!")
            print(f"   Results saved to: {s3_location}")
            
            # Try to download and display results
            try:
                # Use provided s3_client or create new one
                if s3_client is None:
                    import boto3
                    # Check if AWS profile is set
                    aws_profile = os.getenv('AWS_PROFILE')
                    if aws_profile:
                        session = boto3.Session(profile_name=aws_profile)
                        s3 = session.client('s3')
                    else:
                        s3 = boto3.client('s3')
                else:
                    s3 = s3_client
                
                # Parse S3 path
                s3_path = s3_location.replace('s3://', '')
                bucket = s3_path.split('/')[0]
                key = '/'.join(s3_path.split('/')[1:])
                
                # Download the results
                response = s3.get_object(Bucket=bucket, Key=key)
                data = json.loads(response['Body'].read())
                
                # Extract the document data
                if 'documents' in data:
                    docs = data['documents']
                    if docs and len(docs) > 0:
                        extracted_data = docs[0].get('extraction_output', docs[0])
                        display_extracted_data(extracted_data, document_type)
                else:
                    display_extracted_data(data, document_type)
                    
            except Exception as e:
                print(f"   Note: Could not fetch results from S3: {str(e)[:100]}...")
                print(f"   Results are available at: {s3_location}")
        
        # Handle documents in the result directly        
        elif 'documents' in result:
            documents = result.get('documents', [])
            if documents and len(documents) > 0:
                extracted_data = documents[0].get('extraction_output', {})
                display_extracted_data(extracted_data, document_type)
            else:
                print("✅ Processing completed but no documents returned")
        else:
            print("✅ Processing completed")
            print(f"   Result keys: {list(result.keys())}")
    else:
        print("❌ Extraction failed. Check Lambda logs for details.")

def display_extracted_data(extracted_data: Dict, document_type: str = "invoice") -> None:
    """
    Helper function to display extracted data.
    """
    from IPython.display import display, JSON
    
    print("\n📊 Extracted Data (JSON format):")
    print("-"*60)
    
    # Display using IPython's JSON for nice formatting
    display(JSON(extracted_data))

def display_batch_dataframe(df: pd.DataFrame, export_csv: bool = True) -> Optional[str]:
    """
    Display batch processing results as a formatted DataFrame.
    
    Args:
        df: DataFrame with batch processing results
        export_csv: Whether to export results to CSV
        
    Returns:
        CSV filename if exported, None otherwise
    """
    from IPython.display import display
    
    csv_filename = None
    
    if df is not None and not df.empty:
        print("\n📊 Extracted Data as DataFrame:")
        print("-"*60)
        
        # Display full DataFrame with nice formatting
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 50)
        
        display(df)
        
        # Show summary statistics
        print("\n📈 Summary Statistics:")
        print(f"   Total records: {len(df)}")
        
        if 'Extraction Status' in df.columns:
            success_count = len(df[df['Extraction Status'] == 'Success'])
            print(f"   Successfully extracted: {success_count}")
        
        # Calculate totals if Total column exists
        if 'Total' in df.columns:
            df_copy = df.copy()
            df_copy['Total_Amount'] = df_copy['Total'].str.replace('$', '').str.replace(',', '')
            df_copy['Total_Amount'] = pd.to_numeric(df_copy['Total_Amount'], errors='coerce')
            
            total_value = df_copy['Total_Amount'].sum()
            print(f"   Total value: ${total_value:,.2f}")
        
        if 'Customer' in df.columns:
            print(f"   Unique customers: {df['Customer'].nunique()}")
        
        if 'Supplier' in df.columns:
            print(f"   Unique suppliers: {df['Supplier'].nunique()}")

        # Export to CSV if requested
        if export_csv:
            # Create output folder if it doesn't exist
            output_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output_folder')
            os.makedirs(output_folder, exist_ok=True)
            
            csv_filename = f"extraction_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            output_path = os.path.join(output_folder, csv_filename)
            df.to_csv(output_path, index=False)
            print(f"\n💾 Results exported to: {output_path}")
    
    else:
        print("❌ No data to display.")
    
    return output_path if export_csv else None