# AWS Lambda Document Processing Pipeline with LandingAI ADE

A comprehensive document processing pipeline that leverages AWS Lambda, S3, and LandingAI's Agentic Document Extraction (ADE) to automatically parse documents and extract structured data. The system includes two main workflows: medical document parsing with an AI chatbot, and invoice data extraction.

## 🚀 Features

### Part A: Medical Document Processing & AI Chatbot
- **Automatic Document Parsing**: Upload PDFs to S3 and automatically convert them to markdown using LandingAI ADE
- **AWS Bedrock Knowledge Base Integration**: Parsed documents are ingested into a searchable knowledge base
- **Interactive Medical Chatbot**: AI agent with memory capabilities that can answer questions about medical documents
- **Conversation Memory**: The chatbot remembers user preferences and conversation history across sessions

### Part B: Invoice Extraction Pipeline
- **Batch Processing**: Processes multiple invoice PDFs automatically
- **Structured Data Extraction**: Extracts invoice details including:
  - Invoice number, date, customer, supplier
  - Line items, subtotal, tax, total amount
  - Currency and payment status
- **CSV Export**: Consolidated results exported to CSV format
- **Folder Structure Preservation**: Maintains organization of documents in S3

## 📋 Prerequisites

- Python 3.10 (must match Lambda runtime)
- AWS Account with appropriate permissions for:
  - Lambda
  - S3
  - IAM
  - Bedrock
  - CloudWatch Logs
- LandingAI Vision Agent API key
- Local development environment (x86_64 architecture recommended)

## 🛠️ Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd L6
```

2. Install required packages:
```bash
pip install boto3 python-dotenv landingai-ade bedrock-agentcore strands-agents pandas
```

3. Create your environment file (see `.env.example`):
```bash
cp .env.example .env
# Edit .env with your credentials
```

## 📁 Project Structure

```
L6/
├── ade_s3_handler.py           # Lambda function for document parsing
├── batch_invoice_extractor.py  # Lambda function for invoice extraction
├── lambda_helpers.py           # Helper utilities for Lambda deployment
├── L6.ipynb                   # Main Jupyter notebook with workflow
├── .env                       # Environment configuration (create from .env.example)
├── .env.example              # Environment template
├── medical/                  # Medical PDFs to process (optional)
├── invoices/                 # Invoice PDFs to process (optional)
├── ade_lambda.zip            # Deployment package for ADE handler
├── extraction_lambda.zip     # Deployment package for invoice extractor
└── extracted_invoices.csv    # Output from invoice extraction
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# See .env.example for all required variables
VISION_AGENT_API_KEY=your_api_key
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-west-2
S3_BUCKET=your-bucket-name
# ... (see .env.example for complete list)
```

## 📚 Usage

### Quick Start with Jupyter Notebook

1. Open `L6.ipynb` in Jupyter
2. Run cells sequentially to:
   - Set up AWS clients
   - Deploy Lambda functions
   - Configure S3 triggers
   - Process documents
   - Extract invoice data



## 🏗️ Architecture

### Document Processing Flow

```
1. Upload PDF to S3 input/ folder
   ↓
2. S3 trigger invokes ade-s3-handler Lambda
   ↓
3. Lambda parses PDF using LandingAI ADE
   ↓
4. Markdown output saved to S3 output/ folder
   ↓
5. For invoices: batch-invoice-extractor processes markdown
   ↓
6. Structured data exported to CSV in S3 extracted/ folder
```

### S3 Bucket Structure

```
s3://your-bucket/
├── input/              # Upload PDFs here
│   ├── medical/        # Medical documents
│   └── invoices/       # Invoice PDFs
├── output/             # Parsed markdown files
│   ├── medical/        # Medical markdown
│   └── invoices/       # Invoice markdown
└── extracted/          # Extracted structured data (CSV)
```

## 🔍 Key Components

### ade_s3_handler.py
- Triggered by S3 uploads to `input/` folder
- Parses documents using LandingAI ADE
- Preserves folder structure in output
- Skips already processed files (configurable)
- Supports multiple document formats (PDF, images, etc.)

### batch_invoice_extractor.py
- Processes markdown files from `output/invoices/`
- Extracts structured invoice data using Pydantic schemas
- Concurrent processing for better performance
- Generates consolidated CSV reports
- Provides summary statistics

### lambda_helpers.py
- Utility functions for Lambda deployment
- S3 operations (upload, monitor, trigger setup)
- IAM role management
- Package building and deployment
- CloudWatch log monitoring

## 📊 Output Formats

### Medical Documents
- Markdown files with preserved formatting
- Integrated into Bedrock Knowledge Base
- Searchable via AI chatbot

### Invoice Data (CSV)
```csv
source_file,invoice_number,invoice_date,customer,supplier,subtotal,tax,total,currency,status
invoice_1.md,INV123,2024-01-01,Customer Inc,Supplier Co,100.00,10.00,110.00,USD,PAID
```

## 🚦 Monitoring & Debugging

### CloudWatch Logs
- Lambda execution logs: `/aws/lambda/<function-name>`
- Monitor processing status and errors
- View extraction results and statistics

### S3 Monitoring
```python
# Check output folder status
monitor_s3_folder(
    s3_client=s3_client,
    bucket=S3_BUCKET,
    prefix="output/"
)
```

## ⚙️ Advanced Configuration

### Environment Variables for Lambda

- `FORCE_REPROCESS`: Set to "true" to reprocess existing files
- `ADE_MODEL`: Specify ADE model version (default: "dpt-2-latest")
- `INPUT_FOLDER`: S3 input prefix (default: "input/")
- `OUTPUT_FOLDER`: S3 output prefix (default: "output/")

### Memory and Timeout Settings
- Document parsing: 1024 MB RAM, 900s timeout
- Invoice extraction: 3008 MB RAM, 900s timeout

## 🐛 Troubleshooting

### Common Issues

1. **Lambda timeout**: Increase timeout in deployment configuration
2. **Permission errors**: Check IAM role has S3 and Lambda permissions
3. **Package too large**: Use Lambda layers for dependencies
4. **Python version mismatch**: Ensure local Python matches Lambda runtime (3.10)

### Debug Commands
```python
# Check Lambda logs
logs_client.filter_log_events(
    logGroupName="/aws/lambda/ade-s3-handler"
)

# Test S3 trigger
s3_client.head_object(Bucket=bucket, Key="input/test.pdf")

# Verify Lambda configuration
lambda_client.get_function(FunctionName="ade-s3-handler")
```

## 📄 License

This project is for educational purposes. Please ensure you have appropriate licenses for LandingAI ADE and AWS services.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📞 Support

For issues or questions:
- Check CloudWatch logs for Lambda errors
- Verify S3 bucket permissions
- Ensure all environment variables are set correctly
- Review the Jupyter notebook for step-by-step guidance

## 🔄 Updates

- **v1.0**: Initial release with medical document processing and invoice extraction
- Automatic S3 trigger configuration
- Batch processing capabilities
- Memory-enabled chatbot integration