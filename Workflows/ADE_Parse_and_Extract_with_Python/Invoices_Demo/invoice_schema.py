"""
invoice_schema.py
------------------
Defines the `InvoiceExtractionSchema`, a Pydantic-based schema tailored for 
Agentic Document Extraction (ADE) of invoice documents. ADE supports one level of nested schemas.

See documentation at https://docs.landing.ai/ade/ade-extract

This schema classifies and validates structured fields commonly found in invoices, 
including:

- Document metadata (e.g., invoice number, invoice date, order date)
- Customer information (e.g., sold-to name, address, contact)
- Supplier/company information (e.g., name, email, phone, tax identifiers)
- Terms and shipping details (e.g., payment terms, ship date, tracking number)
- Totals summary (e.g., subtotal, tax, shipping, total due)

Each field includes a description to guide the ADE engine in accurate extraction 
and validation. The schema serves as the authoritative structure guiding 
schema-first document parsing and is referenced during ADE pipeline execution.

Usage:
- Passed as the `extraction_model` when calling `parse()` from `agentic_doc`
- Enables consistent and robust parsing across invoice variants
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date

class DocumentInfo(BaseModel):
    invoice_date_raw: str = Field(..., description="Invoice date as a string as found in the document. Do not reformat into another date format.", title="Invoice Date Raw")
    invoice_date: Optional[date] = Field(..., description="Invoice date in standard format YYYY-MM-DD.", title="Invoice Date")
    invoice_number: str = Field(..., description="Invoice number.", title="Invoice Number")
    order_date: Optional[str] = Field(None, description="Order or purchase date.", title="Order Date")
    po_number: Optional[str] = Field(None, description="Customer purchase order (PO) number", title="Customer PO") 
    status: Optional[str] = Field(None, description="Payment status (e.g., PAID, UNPAID).", title="Status")

class CustomerInfo(BaseModel):
    sold_to_name: str = Field(..., description='Name of the customer billed. Can be a person or an organization.', title='Sold To Name')
    sold_to_address: Optional[str] = Field(None, description='Address of the customer billed.', title='Sold To Address')
    customer_email: Optional[str] = Field(None, description='Email address for the customer.', title='Customer Email')
    
class SupplierInfo(BaseModel):
    supplier_name: str = Field(..., description='Name of the supplier company.', title='Supplier Name')
    supplier_address: Optional[str] = Field(None, description='Address of the supplier.', title='Supplier Address') 
    representative: Optional[str] = Field(None, description="Sales representative(s).", title="Representative")
    email: Optional[str] = Field(None, description='Email address of the supplier.', title='Supplier Email')
    phone: Optional[str] = Field(None, description='Phone number of the supplier.', title='Supplier Phone')
    gstin: Optional[str] = Field(None, description='Goods and Services Tax Identification Number (GSTIN) of the supplier (India).', title='Supplier GSTIN')
    pan: Optional[str] = Field(None, description="Permanent Account Number (India).", title="PAN")

class TermsAndShipping(BaseModel):
    payment_terms: Optional[str] = Field(None, description="Payment terms (e.g., Net 30).", title="Payment Terms")
    ship_via: Optional[str] = Field(None, description="Carrier/service (e.g., UPS Ground).", title="Ship Via")
    ship_date: Optional[str] = Field(None, description="Date shipped.", title="Ship Date")
    tracking_number: Optional[str] = Field(None, description="Tracking number.", title="Tracking Number")

class TotalsSummary(BaseModel):
    currency: Optional[str] = Field(None, description="Currency code based on alphabetic ISO codes for currency.", title="Currency")
    total_due_raw: Optional[str] = Field(None, description="Total due as shown in the doc.", title="Total Due Raw")
    total_due: float = Field(..., description="Total amount due as a number (no symbols).", title="Total Due")
    subtotal: Optional[float] = Field(None, description="Subtotal numeric (no symbols).", title="Subtotal")
    tax: Optional[float] = Field(None, description="Tax numeric (no symbols).", title="Tax")
    shipping: Optional[float] = Field(None, description="Shipping numeric (no symbols).", title="Shipping")
    handling_fee: Optional[float] = Field(None, description="Handling fee numeric (no symbols).", title="Handling Fee")
   
class LineItem(BaseModel):
    line_number: Optional[str] = Field(None, description="Printed line number.", title="Line Number")
    sku: Optional[str] = Field(None, description="SKU/Item code/Part number.", title="SKU")
    description: str = Field(..., description="Item/service description.", title="Description")
    quantity: Optional[float] = Field(None, description="Quantity purchased/ Count of units.",title="Quantity")
    unit_price: Optional[float] = Field(None, description="Unit price numeric (no symbols).", title="Unit Price")
    price: Optional[float] = Field(None, description="Single price numeric, if present.", title="Price")
    amount: Optional[float] = Field(None, description="Extended line amount numeric.", title="Amount")
    total: Optional[float] = Field(None, description="Item total numeric.", title="Item Total")
   
class InvoiceExtractionSchema(BaseModel):
    invoice_info: DocumentInfo = Field(description='Key identifiers and dates for the invoice.',title='Invoice Information')
    customer_info: CustomerInfo = Field(description='Details about the customer billed and shipped to.',title='Customer Information')
    company_info: SupplierInfo = Field(description='Details about the issuing company.',title='Supplier Information')
    order_details: TermsAndShipping = Field(description='Key order, payment and shipping information.', title='Order Details')
    totals_summary: TotalsSummary = Field(description='Financial totals by category (e.g. subtitle, total taxes, total shipping).', title='Financial Totals')
    # Use default_factory to avoid nulls in schema and results
    line_items: List[LineItem] = Field(default_factory=list, description="List of items included in the invoice.", title="Line Items")