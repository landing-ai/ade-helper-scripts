"""
Batch Invoice Extractor Lambda Handler
Processes markdown files from S3 and extracts structured invoice data
"""

import os
import json
import asyncio
import boto3
import csv
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
from io import StringIO

from pydantic import BaseModel, Field
from landingai_ade import AsyncLandingAIADE
from landingai_ade.lib import pydantic_to_json_schema


# Invoice Schema Definition
class LineItem(BaseModel):
    description: str = Field(description="Product or service description")
    quantity: Optional[float] = Field(description="Quantity of items", default=None)
    unit_price: Optional[float] = Field(description="Price per unit", default=None)
    amount: float = Field(description="Total amount for this line item")


class Invoice(BaseModel):
    invoice_number: str = Field(description="Invoice number or ID")
    invoice_date: Optional[str] = Field(description="Invoice issue date (YYYY-MM-DD format)", default=None)
    customer: str = Field(description="Customer/Buyer name or company")
    supplier: str = Field(description="Vendor/Seller company name")
    subtotal: Optional[float] = Field(description="Subtotal before tax", default=None)
    tax: Optional[float] = Field(description="Tax amount", default=None)
    total: float = Field(description="Total invoice amount including tax")
    currency: str = Field(description="Currency code (USD, EUR, etc.)", default="USD")
    line_items_count: int = Field(description="Number of line items", default=0)
    status: Optional[str] = Field(description="Payment status (PAID, PENDING, etc.)", default=None)


class InvoiceExtractor:
    """Handles async extraction of invoice data from markdown files"""
    
    def __init__(self, api_key: str, s3_client):
        self.api_key = api_key
        self.s3_client = s3_client
        self.schema = pydantic_to_json_schema(Invoice)
    
    async def extract_single_invoice(
        self, 
        markdown_content: str, 
        filename: str
    ) -> Optional[Dict]:
        """Extract structured data from a single invoice markdown"""
        try:
            async with AsyncLandingAIADE(
                apikey=self.api_key
            ) as client:
                # Save markdown to temp file (ADE requires file path)
                temp_path = Path(f"/tmp/{filename}")
                temp_path.write_text(markdown_content)
                
                # Extract structured data
                result = await client.extract(
                    markdown=temp_path,
                    schema=self.schema
                )
                
                # Clean up temp file
                temp_path.unlink()
                
                # Return extraction with source file
                extraction = result.extraction
                extraction['source_file'] = filename
                return extraction
                
        except Exception as e:
            print(f"⚠️ Error extracting {filename}: {e}")
            return None
    
    async def extract_batch(self, markdown_files: List[Dict]) -> List[Dict]:
        """Extract data from multiple invoices concurrently"""
        tasks = []
        for file_info in markdown_files:
            task = self.extract_single_invoice(
                file_info['content'],
                file_info['filename']
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        # Filter out None results
        return [r for r in results if r is not None]


def lambda_handler(event, context):
    """
    AWS Lambda handler for batch invoice extraction
    Reads markdown files from S3 and extracts structured invoice data
    """
    
    # Environment variables
    VISION_AGENT_API_KEY = os.environ.get("VISION_AGENT_API_KEY")
    S3_BUCKET = os.environ.get("S3_BUCKET")
    INVOICE_MARKDOWN_PATH = os.environ.get("INVOICE_MARKDOWN_PATH", "output/invoices/")
    EXTRACTED_FOLDER = os.environ.get("EXTRACTED_FOLDER", "extracted/")
    
    print(f"📋 Batch Invoice Extraction Lambda")
    print(f"   Source: s3://{S3_BUCKET}/{INVOICE_MARKDOWN_PATH}")
    print(f"   Output: s3://{S3_BUCKET}/{EXTRACTED_FOLDER}")
    
    # Initialize S3 client
    s3_client = boto3.client("s3")
    
    try:
        # List all markdown files in the invoice folder
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix=INVOICE_MARKDOWN_PATH
        )
        
        if "Contents" not in response:
            print("⚠️ No markdown files found in invoice folder")
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "status": "no_files",
                    "message": f"No files found in {INVOICE_MARKDOWN_PATH}"
                })
            }
        
        # Filter for markdown files
        markdown_files = []
        for obj in response["Contents"]:
            key = obj["Key"]
            if key.endswith(".md") and key != INVOICE_MARKDOWN_PATH:
                print(f"   Found: {key}")
                
                # Download markdown content
                md_response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
                content = md_response["Body"].read().decode("utf-8")
                
                markdown_files.append({
                    "filename": os.path.basename(key),
                    "content": content
                })
        
        print(f"\n📄 Found {len(markdown_files)} markdown files to process")
        
        if not markdown_files:
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "status": "no_markdown",
                    "message": "No markdown files found"
                })
            }
        
        # Create timestamp for this batch
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Initialize extractor
        extractor = InvoiceExtractor(
            api_key=VISION_AGENT_API_KEY,
            s3_client=s3_client
        )
        
        # Extract data from all invoices
        print(f"\n🤖 Starting extraction for {len(markdown_files)} invoices...")
        
        # Create event loop for async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        extracted_invoices = loop.run_until_complete(
            extractor.extract_batch(markdown_files)
        )
        loop.close()
        
        # Process results if we have extracted data
        if extracted_invoices:
            # Define column order
            column_order = [
                'source_file', 'invoice_number', 'invoice_date', 
                'customer', 'supplier', 'subtotal', 'tax', 'total',
                'currency', 'line_items_count', 'status'
            ]
            
            # Display summary
            print(f"\n📊 Extracted Invoice Data:")
            print("="*80)
            
            # Calculate summary statistics
            total_value = sum(inv.get('total', 0) for inv in extracted_invoices)
            unique_customers = len(set(inv.get('customer', '') for inv in extracted_invoices if inv.get('customer')))
            unique_suppliers = len(set(inv.get('supplier', '') for inv in extracted_invoices if inv.get('supplier')))
            
            print(f"\n📈 Summary Statistics:")
            print(f"   Total invoices: {len(extracted_invoices)}")
            print(f"   Total value: ${total_value:,.2f}")
            print(f"   Unique customers: {unique_customers}")
            print(f"   Unique suppliers: {unique_suppliers}")
            
            
            # Save consolidated CSV (always created)
            combined_csv_key = f"{EXTRACTED_FOLDER}batch_all_invoices_{timestamp}.csv"
            csv_buffer = StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=column_order)
            writer.writeheader()
            
            for invoice_data in extracted_invoices:
                row_data = {col: invoice_data.get(col, '') for col in column_order}
                writer.writerow(row_data)
            
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=combined_csv_key,
                Body=csv_buffer.getvalue(),
                ContentType="text/csv"
            )
            
            print(f"\n✅ Saved consolidated CSV: {combined_csv_key}")
            print(f"   📊 Contains all {len(extracted_invoices)} invoices in one file")
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "summary": {
                        "processed": len(extracted_invoices),
                        "total_value": total_value,
                        "csv_location": f"s3://{S3_BUCKET}/{combined_csv_key}"
                    },
                    "extractions": extracted_invoices
                })
            }
        else:
            print("⚠️ No data extracted from any invoices")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "no_extractions",
                    "message": "No data could be extracted from the markdown files"
                })
            }
            
    except Exception as e:
        print(f"❌ Lambda error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error": str(e)
            })
        }