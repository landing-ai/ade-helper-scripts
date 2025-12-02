"""
Lambda Deployment Helper Functions
Utilities for deploying and managing AWS Lambda functions
"""

import boto3
import json
import time
import subprocess
import zipfile
import os
from pathlib import Path
from typing import Dict, List, Optional, Any


def create_or_update_lambda_role(
    iam_client, 
    role_name: str, 
    description: str = "Lambda execution role"
) -> str:
    """
    Create or reuse IAM role for Lambda execution
    
    Returns:
        role_arn: ARN of the created/existing role
    """
    assume_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        role = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_policy),
            Description=description
        )
        print(f"✅ Created IAM role: {role_name}")
        role_arn = role["Role"]["Arn"]
        
        # Attach necessary policies
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        )
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess"
        )
        
        # Wait for role to propagate
        time.sleep(10)
        
    except iam_client.exceptions.EntityAlreadyExistsException:
        role = iam_client.get_role(RoleName=role_name)
        role_arn = role["Role"]["Arn"]
        print(f"ℹ️ Using existing role: {role_name}")
    
    return role_arn


def create_deployment_package(
    source_files: List[str],
    requirements: List[str],
    output_zip: str,
    package_dir: str = "lambda_package"
) -> str:
    """
    Build Lambda deployment package with dependencies
    
    Args:
        source_files: List of Python files to include
        requirements: List of pip packages to install
        output_zip: Name of output zip file
        package_dir: Temporary directory for building package
    
    Returns:
        Path to created zip file
    """
    print(f"📦 Creating deployment package: {output_zip}")
    
    # Clean and create package directory
    subprocess.run(f"rm -rf {package_dir}", shell=True)
    subprocess.run(f"mkdir -p {package_dir}", shell=True)
    
    # Install requirements
    if requirements:
        print(f"   Installing dependencies: {', '.join(requirements)}")
        req_string = " ".join(requirements)
        result = subprocess.run(
            f"pip install --quiet {req_string} -t {package_dir}",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"⚠️ Warning: Some dependencies may have failed to install")
            print(result.stderr)
    
    # Copy source files
    for source_file in source_files:
        print(f"   Adding source: {source_file}")
        subprocess.run(f"cp {source_file} {package_dir}/", shell=True)
    
    # Create zip
    print(f"   Creating zip archive...")
    subprocess.run(
        f"cd {package_dir} && zip -r ../{output_zip} . > /dev/null 2>&1",
        shell=True
    )
    
    # Cleanup
    subprocess.run(f"rm -rf {package_dir}", shell=True)
    
    # Get zip size
    zip_size = os.path.getsize(output_zip) / (1024 * 1024)
    print(f"✅ Package created: {output_zip} ({zip_size:.1f} MB)")
    
    return output_zip


def deploy_lambda_function(
    lambda_client,
    function_name: str,
    zip_file: str,
    role_arn: str,
    handler: str,
    env_vars: Dict[str, str],
    runtime: str = "python3.10",
    timeout: int = 900,
    memory_size: int = 3008,
    architectures: List[str] = ["x86_64"]
) -> Dict:
    """
    Deploy or update Lambda function
    
    Returns:
        Function configuration dict
    """
    print(f"🚀 Deploying Lambda function: {function_name}")
    
    # Read zip file
    with open(zip_file, "rb") as f:
        zipped_code = f.read()
    
    try:
        # Try to create new function
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime=runtime,
            Role=role_arn,
            Handler=handler,
            Code={"ZipFile": zipped_code},
            Timeout=timeout,
            MemorySize=memory_size,
            Architectures=architectures,
            Environment={"Variables": env_vars},
            Publish=True
        )
        print(f"✅ Lambda function created: {function_name}")
        
    except lambda_client.exceptions.ResourceConflictException:
        # Function exists, update it
        print(f"ℹ️ Function exists, updating...")
        
        # Update code
        lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zipped_code,
            Publish=True
        )
        print("   Code updated, waiting for deployment...")
        time.sleep(10)
        
        # Update configuration
        response = lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={"Variables": env_vars},
            Timeout=timeout,
            MemorySize=memory_size,
            Handler=handler,
            Runtime=runtime
        )
        print(f"✅ Lambda function updated: {function_name}")
    
    return response


def setup_s3_trigger(
    s3_client,
    lambda_client,
    bucket: str,
    prefix: str,
    function_name: str,
    suffix: Optional[str] = None
) -> None:
    """
    Configure S3 event trigger for Lambda
    
    Args:
        bucket: S3 bucket name
        prefix: Folder prefix to trigger on
        function_name: Lambda function to trigger
        suffix: Optional file suffix filter (e.g., '.pdf')
    """
    print(f"⚙️ Setting up S3 trigger: s3://{bucket}/{prefix} → {function_name}")
    
    # Get Lambda function ARN
    function_config = lambda_client.get_function(FunctionName=function_name)
    function_arn = function_config["Configuration"]["FunctionArn"]
    
    # Give S3 permission to invoke the Lambda
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId="s3invokepermission",
            Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com",
            SourceArn=f"arn:aws:s3:::{bucket}"
        )
        print(f"   ✅ Added invoke permission for S3")
    except Exception as e:
        print(f"   ℹ️ Permission may already exist: {e}")
    
    # Configure filter rules
    filter_rules = [{"Name": "prefix", "Value": prefix}]
    if suffix:
        filter_rules.append({"Name": "suffix", "Value": suffix})
    
    # Attach the notification configuration to S3
    # Note: This replaces ALL existing Lambda notifications - use carefully
    s3_client.put_bucket_notification_configuration(
        Bucket=bucket,
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {
                    "LambdaFunctionArn": function_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {"Key": {"FilterRules": filter_rules}}
                }
            ]
        }
    )
    
    print(f"✅ S3 trigger set for s3://{bucket}/{prefix} → {function_name}")


def invoke_lambda_sync(
    lambda_client,
    function_name: str,
    payload: Optional[Dict] = None,
    show_logs: bool = True
) -> Dict:
    """
    Invoke Lambda synchronously and wait for response
    
    Args:
        function_name: Name of Lambda function
        payload: Optional JSON payload
        show_logs: Whether to print logs
    
    Returns:
        Response from Lambda function
    """
    print(f"⚡ Invoking Lambda: {function_name}")
    start_time = time.time()
    
    invoke_params = {
        "FunctionName": function_name,
        "InvocationType": "RequestResponse",
        "LogType": "Tail" if show_logs else "None"
    }
    
    if payload:
        invoke_params["Payload"] = json.dumps(payload)
    
    response = lambda_client.invoke(**invoke_params)
    
    # Parse response
    status_code = response["StatusCode"]
    
    if "Payload" in response:
        result = json.loads(response["Payload"].read())
    else:
        result = {}
    
    elapsed = time.time() - start_time
    
    if status_code == 200:
        print(f"✅ Lambda completed successfully in {elapsed:.1f} seconds")
    else:
        print(f"⚠️ Lambda returned status code: {status_code}")
    
    # Show logs if requested
    if show_logs and "LogResult" in response:
        import base64
        log_data = base64.b64decode(response["LogResult"]).decode("utf-8")
        print("\n📋 Lambda Logs:")
        print("-" * 60)
        for line in log_data.split("\n")[-20:]:  # Last 20 lines
            if line.strip():
                print(line)
        print("-" * 60)
    
    return result


def monitor_s3_folder(
    s3_client,
    bucket: str,
    prefix: str,
    expected_count: Optional[int] = None
) -> List[str]:
    """
    Monitor S3 folder for files
    
    Args:
        bucket: S3 bucket name
        prefix: Folder prefix to monitor
        expected_count: Optional expected number of files
    
    Returns:
        List of file keys found
    """
    print(f"📁 Monitoring s3://{bucket}/{prefix}")
    
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    
    files = []
    if "Contents" in response:
        for obj in response["Contents"]:
            if not obj["Key"].endswith("/"):
                files.append(obj["Key"])
    
    print(f"   Found {len(files)} files")
    
    if expected_count and len(files) < expected_count:
        print(f"   ⏳ Waiting for {expected_count - len(files)} more files...")
    
    return files


def upload_folder_to_s3(
    s3_client,
    local_folder: str,
    s3_prefix: str,
    bucket: str,
    file_extensions: Optional[List[str]] = None,
    skip_existing: bool = True
) -> int:
    """
    Upload entire folder to S3
    
    Args:
        local_folder: Local folder path
        s3_prefix: S3 prefix for uploads
        bucket: S3 bucket name
        file_extensions: Optional list of extensions to filter
        skip_existing: Skip files that already exist in S3 (default True)
    
    Returns:
        Number of files uploaded
    """
    print(f"📤 Uploading {local_folder} → s3://{bucket}/{s3_prefix}")
    if skip_existing:
        print("   (Skipping files that already exist in S3)")
    
    uploaded = 0
    skipped = 0
    local_path = Path(local_folder)
    
    if not local_path.exists():
        print(f"❌ Folder not found: {local_folder}")
        return 0
    
    files = list(local_path.glob("**/*"))
    
    for file_path in files:
        if file_path.is_file():
            # Check extension filter
            if file_extensions and file_path.suffix.lower() not in file_extensions:
                continue
            
            # Calculate S3 key
            relative_path = file_path.relative_to(local_path)
            s3_key = f"{s3_prefix}{relative_path}"
            
            # Check if file already exists in S3
            if skip_existing:
                try:
                    s3_client.head_object(Bucket=bucket, Key=s3_key)
                    print(f"   ⏭️ Skipping (already exists): {relative_path}")
                    skipped += 1
                    continue
                except s3_client.exceptions.ClientError:
                    # File doesn't exist, proceed with upload
                    pass
            
            # Upload file
            print(f"   ⬆️ Uploading: {relative_path}")
            s3_client.upload_file(str(file_path), bucket, s3_key)
            uploaded += 1
    
    # Summary
    if skipped > 0:
        print(f"✅ Uploaded {uploaded} files, skipped {skipped} existing files")
    else:
        print(f"✅ Uploaded {uploaded} files")
    
    return uploaded


def monitor_lambda_processing(
    logs_client,
    s3_client,
    bucket_name: str,
    function_name: str = "ade-s3-handler",
    lookback_minutes: int = 10,
    output_prefix: str = "output/"
) -> Dict:
    """
    Monitor Lambda processing and display results.
    
    Args:
        logs_client: Boto3 CloudWatch Logs client
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        function_name: Lambda function name to monitor
        lookback_minutes: How many minutes back to look in logs
        output_prefix: S3 prefix for output files
    
    Returns:
        Dict with processing statistics
    """
    import time
    
    log_group = f"/aws/lambda/{function_name}"
    
    print(f"⏳ Monitoring Lambda processing...")
    print("   Press Ctrl+C to stop monitoring\n")
    
    # Track processed files
    processed_files = set()
    processing_files = set()
    skipped_files = set()
    error_files = set()
    start_time = int((time.time() - (lookback_minutes * 60)) * 1000)
    
    try:
        while True:
            resp = logs_client.filter_log_events(logGroupName=log_group, startTime=start_time)
            events = resp.get("events", [])
            
            for event in events:
                message = event["message"].strip()
                
                # Track successful completions
                if "🎉 Completed pipeline for" in message:
                    file_name = message.split("Completed pipeline for ")[1].split(" →")[0]
                    if file_name not in processed_files:
                        processed_files.add(file_name)
                        print(f"✅ Processed: {file_name}")
                
                # Track files being processed (but don't print)
                elif "🤖 Starting ADE parsing for" in message:
                    file_name = message.split("parsing for ")[1].split(" (")[0]
                    processing_files.add(file_name)
                
                # Track skipped files
                elif "⏭️ Skipping" in message and "already processed" in message:
                    file_name = message.split("Skipping ")[1].split(" -")[0]
                    if file_name not in skipped_files:
                        skipped_files.add(file_name)
                        print(f"⏭️ Skipped (already exists): {file_name}")
                
                # Show errors
                elif "❌ Error processing" in message:
                    print(f"   {message}")
                    try:
                        file_name = message.split("Error processing ")[1].split(":")[0]
                        error_files.add(file_name)
                    except:
                        pass
                
                start_time = max(start_time, event["timestamp"] + 1)
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        print(f"\n⛔ Monitoring stopped by user")
    
    # Show summary from logs
    print(f"\n📊 Lambda Processing Summary:")
    print(f"   Processed: {len(processed_files)} files")
    print(f"   Skipped: {len(skipped_files)} files")
    print(f"   Errors: {len(error_files)} files")
    
    if processed_files:
        print("\n   Files processed in this session:")
        for f in sorted(processed_files):
            print(f"   - {f}")
    
    # Check what's actually in the output folder
    print(f"\n📁 Checking S3 {output_prefix} folder...")
    response = s3_client.list_objects_v2(
        Bucket=bucket_name,
        Prefix=output_prefix,
        MaxKeys=1000  # Get all files
    )
    
    output_files = []
    if "Contents" in response:
        output_files = [obj["Key"] for obj in response["Contents"] if not obj["Key"].endswith("/")]
        print(f"   Total files in {output_prefix}: {len(output_files)}")
        
        # Organize by folder
        folders = {}
        for key in output_files:
            parts = key.split("/")
            if len(parts) > 2:  # Has subfolder
                folder = parts[1]
                if folder not in folders:
                    folders[folder] = []
                folders[folder].append(key)
            elif len(parts) == 2:  # Direct in output/
                if "root" not in folders:
                    folders["root"] = []
                folders["root"].append(key)
        
        # Display organized summary
        if folders:
            print(f"\n   Files by folder:")
            for folder, files in sorted(folders.items()):
                if folder == "root":
                    print(f"   {output_prefix} (root): {len(files)} files")
                else:
                    print(f"   {output_prefix}{folder}/: {len(files)} files")
            
            # Option to show all files
            show_all = input("\n   Show all output files? (y/n): ").lower() == 'y'
            if show_all:
                print("\n   All output files:")
                for key in sorted(output_files):
                    print(f"   - {key}")
    else:
        print(f"   No files found in {output_prefix} yet")
    
    return {
        "processed": len(processed_files),
        "skipped": len(skipped_files),
        "errors": len(error_files),
        "total_output_files": len(output_files),
        "processed_files": list(processed_files),
        "output_files": output_files
    }


def display_extraction_results(response: Dict) -> None:
    """
    Display extraction results in formatted table
    
    Args:
        response: Response from extraction Lambda
    """
    import pandas as pd
    
    if not response or "summary" not in response:
        print("❌ No results to display")
        return
    
    summary = response.get("summary", {})
    preview = response.get("dataframe_preview", [])
    
    print("\n" + "="*80)
    print("📊 EXTRACTION RESULTS")
    print("="*80)
    
    # Display summary
    print(f"\n📈 Summary Statistics:")
    print(f"   Documents processed: {summary.get('processed', 0)}")
    print(f"   Total value: ${summary.get('total_value', 0):,.2f}")
    print(f"   CSV location: {summary.get('csv_location', 'N/A')}")
    
    # Display preview table if available
    if preview:
        df = pd.DataFrame(preview)
        print("\n📋 Invoice Data Preview (first 10):")
        print("-"*80)
        print(df.to_string(index=False))
    
    print("\n" + "="*80)