import os
import json
import boto3
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote_plus
from landingai_ade import LandingAIADE

s3 = boto3.client("s3")

VISION_AGENT_API_KEY = os.environ.get("VISION_AGENT_API_KEY")
ADE_MODEL = os.environ.get("ADE_MODEL", "dpt-2-latest")
INPUT_FOLDER = os.environ.get("INPUT_FOLDER", "input/")
OUTPUT_FOLDER = os.environ.get("OUTPUT_FOLDER", "output/")
FORCE_REPROCESS = os.environ.get("FORCE_REPROCESS", "false").lower() == "true"

client = LandingAIADE(apikey=VISION_AGENT_API_KEY)

def ensure_s3_folders(bucket: str):
    for folder in [INPUT_FOLDER, OUTPUT_FOLDER]:
        try:
            s3.put_object(Bucket=bucket, Key=folder)
            print(f"✅ Ensured folder exists: s3://{bucket}/{folder}")
        except Exception as e:
            print(f"⚠️ Could not ensure folder {folder}: {e}")

def ade_handler(event, context):
    """
    AWS Lambda handler for automatically parsing documents uploaded to S3/input/
    and saving Markdown results to S3/output/ with preserved folder structure.
    
    Examples:
    - input/invoices/doc.pdf → output/invoices/doc.pdf.md
    - input/contracts/file.pdf → output/contracts/file.pdf.md
    - input/doc.pdf → output/doc.pdf.md
    """
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        
        # Skip folder creation events
        if key.endswith("/"):
            print(f"⏩ Skipping folder: {key}")
            continue
            
        doc_id = os.path.basename(key)
        
        # Skip if no filename
        if not doc_id:
            print(f"⏩ Skipping empty filename: {key}")
            continue

        print(f"🚀 Lambda triggered for new upload: {doc_id}")
        ensure_s3_folders(bucket)

        if not key.startswith(INPUT_FOLDER):
            print(f"⏩ Skipping non-input file: {key}")
            continue

        # Extract relative path from input folder to preserve folder structure
        relative_path = key[len(INPUT_FOLDER):] if key.startswith(INPUT_FOLDER) else key
        
        # Get the directory structure and filename
        path_parts = Path(relative_path)
        subfolder = str(path_parts.parent) if path_parts.parent != Path('.') else ''
        filename = path_parts.name
        
        # Remove the original extension (e.g., .pdf) and add .md
        # This converts "document.pdf" to "document.md" instead of "document.pdf.md"
        filename_without_ext = Path(filename).stem  # Gets filename without extension
        
        # Build output key preserving folder structure
        if subfolder and subfolder != '.':
            output_key = f"{OUTPUT_FOLDER}{subfolder}/{filename_without_ext}.md"
        else:
            output_key = f"{OUTPUT_FOLDER}{filename_without_ext}.md"

        # Check if output file already exists (unless force reprocess is enabled)
        if not FORCE_REPROCESS:
            try:
                s3.head_object(Bucket=bucket, Key=output_key)
                print(f"⏭️ Skipping {doc_id} - already processed (output exists: {output_key})")
                results.append({
                    "source": f"s3://{bucket}/{key}",
                    "output": f"s3://{bucket}/{output_key}",
                    "status": "skipped",
                    "reason": "already_processed"
                })
                continue
            except s3.exceptions.ClientError:
                # File doesn't exist, proceed with processing
                pass

        try:
            print(f"📥 Fetching s3://{bucket}/{key}")
            obj = s3.get_object(Bucket=bucket, Key=key)
            file_bytes = obj["Body"].read()

            tmp_path = Path("/tmp") / filename
            tmp_path.write_bytes(file_bytes)

            # Start parsing
            print(f"🤖 Starting ADE parsing for {doc_id} (model={ADE_MODEL})")
            response = client.parse(document=tmp_path, model=ADE_MODEL)
            markdown = response.markdown
            print(f"✅ Finished parsing document: {doc_id}")

            print(f"⬆️ Uploading parsed Markdown → s3://{bucket}/{output_key}")
            if subfolder and subfolder != '.':
                print(f"   Preserved folder structure: {subfolder}/")
            s3.put_object(
                Bucket=bucket,
                Key=output_key,
                Body=markdown.encode("utf-8"),
                ContentType="text/markdown"
            )

            results.append({
                "source": f"s3://{bucket}/{key}",
                "output": f"s3://{bucket}/{output_key}",
                "status": "success"
            })

            print(f"🎉 Completed pipeline for {doc_id} → {output_key} (clean name: {filename_without_ext}.md)")

        except Exception as e:
            print(f"❌ Error processing {doc_id}: {e}")
            results.append({
                "source": f"s3://{bucket}/{key}",
                "error": str(e),
                "status": "failed"
            })

    print("🏁 All records processed.")
    return {"status": "ok", "results": results}