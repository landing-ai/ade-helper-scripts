"""
Configuration and Schemas for ADE Lambda S3
============================================
Environment configuration using pydantic-settings and extraction schemas.
"""

import os
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import date
from pathlib import Path

# Try to import BaseSettings from the correct location
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

# ===========================
# Environment Configuration
# ===========================

class Settings(BaseSettings):
    """Environment configuration using pydantic-settings for .env support."""
    
    # AWS Configuration
    aws_profile: str = Field(default="default", description="AWS SSO profile name")
    aws_region: str = Field(default="us-east-2", description="AWS region")
    aws_account_id: Optional[str] = Field(default=None, description="AWS account ID")
    
    # S3 Configuration
    bucket_name: str = Field(..., description="S3 bucket name for documents")
    
    # Lambda Configuration
    function_name: str = Field(default="ade-lambda-s3", description="Lambda function name")
    ecr_repo: str = Field(default="ade-lambda-s3", description="ECR repository name")
    role_name: str = Field(default="ade-lambda-s3-role", description="IAM role name")
    
    # LandingAI Configuration
    vision_agent_api_key: str = Field(..., description="LandingAI API key")
    
    # Processing Defaults
    extraction_mode: bool = Field(default=False, description="Default extraction mode")
    document_type: str = Field(default="invoice", description="Default document type")
    max_pages: int = Field(default=50, description="Maximum pages to process")
    timeout_seconds: int = Field(default=300, description="Lambda timeout in seconds")
    
    # Local Configuration
    project_path: str = Field(default_factory=lambda: str(Path.cwd()), description="Project path")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """
    Get settings instance with environment variables loaded.
    Loads from .env file if it exists, otherwise uses environment variables.
    """
    # Force reload of dotenv to ensure fresh values
    from dotenv import load_dotenv
    
    # Look for .env in current directory first, then parent directories
    current_dir = Path.cwd()
    env_file = None
    
    # Check current directory
    if (current_dir / ".env").exists():
        env_file = current_dir / ".env"
    # Check parent directory (in case running from Workflows/ADE_Lambda_S3)
    elif (current_dir.parent / ".env").exists():
        env_file = current_dir.parent / ".env"
    # Check grandparent directory
    elif (current_dir.parent.parent / ".env").exists():
        env_file = current_dir.parent.parent / ".env"
    
    # Explicitly load the .env file
    if env_file:
        load_dotenv(env_file, override=True)
    
    return Settings(_env_file=env_file)

# ===========================
# Example .env Template
# ===========================

ENV_TEMPLATE = """
# AWS Configuration
AWS_PROFILE=your-sso-profile-name
AWS_REGION=us-east-2
AWS_ACCOUNT_ID=

# S3 Configuration
BUCKET_NAME=your-unique-bucket-name

# Lambda Configuration
FUNCTION_NAME=ade-lambda-s3
ECR_REPO=ade-lambda-s3
ROLE_NAME=ade-lambda-s3-role

# LandingAI Configuration
VISION_AGENT_API_KEY=YOUR_VISION_AGENT_API_KEY

# Processing Defaults
EXTRACTION_MODE=false
DOCUMENT_TYPE=invoice
MAX_PAGES=50
TIMEOUT_SECONDS=300

# Local Configuration
PROJECT_PATH=/path/to/your/ade-lambda-s3
"""

def create_env_template(filepath: str = ".env.example"):
    """Create a .env template file."""
    with open(filepath, 'w') as f:
        f.write(ENV_TEMPLATE.strip())
    print(f"✅ Created {filepath} template")
    print(f"   Copy to .env and fill in your values")

if __name__ == "__main__":
    # Example usage
    print("📋 Configuration Module")
    print("=" * 60)
    
    # Create .env template if needed
    if not Path(".env.example").exists():
        create_env_template()
    
    # Try loading settings
    try:
        settings = get_settings()
        print("\n✅ Settings loaded successfully")
        print(f"   Bucket: {settings.bucket_name}")
        print(f"   Function: {settings.function_name}")
        print(f"   Region: {settings.aws_region}")
        print(f"   Profile: {settings.aws_profile}")
    except Exception as e:
        print(f"\n⚠️  Configuration error: {e}")
        print("   Please check your .env file or environment variables")

# ===========================
# Document Extraction Schemas
# ===========================

# Invoice Schema Components
class InvoiceInfo(BaseModel):
    """Invoice document metadata."""
    invoice_date_raw: str = Field(..., description="Invoice date as found in the document")
    invoice_date: Optional[date] = Field(None, description="Invoice date in YYYY-MM-DD format")
    invoice_number: str = Field(..., description="Invoice number")
    order_date: Optional[str] = Field(None, description="Order or purchase date")
    po_number: Optional[str] = Field(None, description="Customer purchase order number")
    status: Optional[str] = Field(None, description="Payment status (PAID, UNPAID)")

class CustomerInfo(BaseModel):
    """Customer information."""
    sold_to_name: str = Field(..., description="Name of customer billed")
    sold_to_address: Optional[str] = Field(None, description="Customer address")
    customer_email: Optional[str] = Field(None, description="Customer email")

class SupplierInfo(BaseModel):
    """Supplier/company information."""
    supplier_name: str = Field(..., description="Name of supplier company")
    supplier_address: Optional[str] = Field(None, description="Supplier address")
    representative: Optional[str] = Field(None, description="Sales representative")
    email: Optional[str] = Field(None, description="Supplier email")
    phone: Optional[str] = Field(None, description="Supplier phone")

class TotalsSummary(BaseModel):
    """Financial totals."""
    currency: Optional[str] = Field(None, description="Currency code (USD, EUR, etc)")
    total_due: float = Field(..., description="Total amount due")
    subtotal: Optional[float] = Field(None, description="Subtotal amount")
    tax: Optional[float] = Field(None, description="Tax amount")
    shipping: Optional[float] = Field(None, description="Shipping cost")

class LineItem(BaseModel):
    """Invoice line item."""
    description: str = Field(..., description="Item/service description")
    quantity: Optional[float] = Field(None, description="Quantity")
    unit_price: Optional[float] = Field(None, description="Unit price")
    amount: Optional[float] = Field(None, description="Line amount")
    sku: Optional[str] = Field(None, description="SKU or product code")

class InvoiceExtractionSchema(BaseModel):
    """Complete invoice extraction schema."""
    invoice_info: InvoiceInfo
    customer_info: CustomerInfo
    company_info: SupplierInfo
    totals_summary: TotalsSummary
    line_items: List[LineItem] = Field(default_factory=list, description="Invoice line items")

# Purchase Order Schema
class PurchaseOrderSchema(BaseModel):
    """Purchase order extraction schema."""
    po_number: str = Field(..., description="Purchase order number")
    po_date: Optional[date] = Field(None, description="PO date")
    vendor_name: str = Field(..., description="Vendor name")
    ship_to_address: Optional[str] = Field(None, description="Shipping address")
    total_amount: float = Field(..., description="Total PO amount")
    line_items: List[LineItem] = Field(default_factory=list)

# Receipt Schema
class ReceiptSchema(BaseModel):
    """Receipt extraction schema."""
    store_name: str = Field(..., description="Store/merchant name")
    transaction_date: Optional[date] = Field(None, description="Transaction date")
    transaction_time: Optional[str] = Field(None, description="Transaction time")
    total_amount: float = Field(..., description="Total amount")
    payment_method: Optional[str] = Field(None, description="Payment method")
    items: List[LineItem] = Field(default_factory=list)

# ===========================
# Schema Registry & Helpers
# ===========================

SCHEMAS = {
    "invoice": InvoiceExtractionSchema,
    "purchase_order": PurchaseOrderSchema,
    "receipt": ReceiptSchema
}

def get_schema(document_type: str):
    """Get schema by document type."""
    return SCHEMAS.get(document_type.lower())

def export_schema_json(document_type: str) -> dict:
    """Export schema as JSON schema for config."""
    schema_class = get_schema(document_type)
    if schema_class:
        return schema_class.schema()
    return {}
