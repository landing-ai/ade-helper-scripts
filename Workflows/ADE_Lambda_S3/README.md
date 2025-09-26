# 🚀 ADE Lambda S3 - Serverless Document Processing

[![LandingAI](https://img.shields.io/badge/LandingAI-ADE-blue)](https://landing.ai)
[![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-orange)](https://aws.amazon.com/lambda/)
[![Docker](https://img.shields.io/badge/Docker-Container-blue)](https://www.docker.com/)

Deploy LandingAI's **Agentic Document Extraction (ADE)** as a serverless Lambda function to automatically process documents from S3 buckets at scale.

## ✨ Features

- **Two Processing Modes**: 
  - **Parsing**: Parse entire document and output hierarchical json
  - **Extraction**: Extract structured data using Pydantic schemas
- **Batch Processing**: Process entire S3 folders with progress bar
- **Auto-Triggers**: Automatic processing on S3 uploads
- **Customizable Schemas**: Invoice, Purchase Order, Receipt, or custom schemas
- **Clean Output**: DataFrames and formatted tables for analysis
- **Optimized Timeouts**: 15-minute client timeout for large batch operations

## 📁 Essential Files

```
ade-lambda-s3/
├── 📓 ADE_Lambda_S3.ipynb        # Main notebook with all examples
├── 📓 S3_Trigger.ipynb           # S3 trigger setup notebook
├── 🐍 handler.py                 # Lambda handler code
├── 🐍 utils.py                   # All utility functions (AWS, S3, processing)
├── 🐍 config.py                  # Settings and schema definitions
├── 📄 .env.example               # Create your configuration (.env)from this template
├── 📄 requirements.txt           # Python dependencies
├── 🐳 Dockerfile                 # Container configuration
├── 🔨 build.sh                   # Build & push script
├── 🚀 deploy.sh                  # Lambda deployment script
└── 📖 README.md                  # This file
```

## 🎯 Quick Start

### 1. Setup Configuration

```bash
# Clone repository
git clone https://github.com/landing-ai/ade-lambda-s3.git
cd ade-lambda-s3
```

```bash
# Create configuration from template
cp .env.example .env

# Edit .env with your settings, including the following:
# - VISION_AGENT_API_KEY: Your LandingAI API key
# - AWS_PROFILE: Your AWS profile name  
# - BUCKET_NAME: Your S3 bucket
# - AWS_REGION: Your AWS region (default: us-east-2)
```



```bash
# Load configuration from .env
eval $(python3 -c "
from config import get_settings
s = get_settings()
print(f'export AWS_PROFILE={s.aws_profile}')
print(f'export AWS_REGION={s.aws_region}')
print(f'export AWS_ACCOUNT_ID={s.aws_account_id}')
print(f'export FUNCTION_NAME={s.function_name}')
print(f'export ECR_REPO={s.ecr_repo}')
print(f'export ROLE_NAME={s.role_name}')
print(f'export BUCKET_NAME={s.bucket_name}')
print(f'export VISION_AGENT_API_KEY={s.vision_agent_api_key}')
")
```


## 🐳 Docker Build & Deployment Explained

### Understanding the Process

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Docker    │ ---> │     ECR     │ ---> │   Lambda    │
│   Image     │      │ Repository  │      │  Function   │
└─────────────┘      └─────────────┘      └─────────────┘
     Build              Push                  Deploy
```

### Step 1: Dockerfile Creation

Copy the following into a `Dockerfile`. 
We use AWS Lambda's official Python runtime:

```dockerfile
# Use AWS Lambda Python 3.11 base image
FROM public.ecr.aws/lambda/python:3.11

# Install Python dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy Lambda handler and other files the handler depends on
COPY handler.py ${LAMBDA_TASK_ROOT}
COPY config.py /var/task

# Set the handler function
CMD ["handler.lambda_handler"]

```

### Step 2: Build Script (`build.sh`) Breakdown


#### Alternative 1: Run bash script directly
```bash
# Build Docker image and push to ECR
./build.sh --no-cache # allow for a clean rebuid
```
#### Alternative 2: Run the following commands in terminal


```bash
#!/bin/bash

# 1. Build Docker image locally
Docker build --platform linux/arm64 -t ${FUNCTION_NAME}:latest .

# 2. Authenticate Docker to ECR
aws ecr get-login-password --region ${AWS_REGION} \
  --profile ${AWS_PROFILE} | \
  docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# 3. Create ECR repository if it doesn't exist
aws ecr describe-repositories \
  --repository-names ${FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --profile ${AWS_PROFILE} 2>/dev/null || \
aws ecr create-repository \
  --repository-name ${FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --profile ${AWS_PROFILE}

# 4. Tag image for ECR
docker tag ${FUNCTION_NAME}:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${FUNCTION_NAME}:latest

# 5. Push image to ECR
docker push \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${FUNCTION_NAME}:latest
```

### Step 3: Deploy Script (`deploy.sh`) Breakdown

#### Alternative 1: Run bash script directly
```bash
# Build Docker image and push to ECR
./deploy.sh 
```
#### Alternative 2: Bash script breakdown- run the following commands in th terminal

```bash
#!/bin/bash

# 1. Create IAM role for Lambda (if needed)
aws iam create-role \
  --role-name ${FUNCTION_NAME}-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }' \
  --profile ${AWS_PROFILE}

# 2. Attach necessary policies
aws iam attach-role-policy \
  --role-name ${FUNCTION_NAME}-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
  --profile ${AWS_PROFILE}

# 3. Create or update Lambda function
aws lambda create-function \
  --function-name ${FUNCTION_NAME} \
  --package-type Image \
  --code ImageUri=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${FUNCTION_NAME}:latest \
  --role arn:aws:iam::${AWS_ACCOUNT_ID}:role/${FUNCTION_NAME}-role \
  --timeout 300 \
  --memory-size 1024 \
  --environment Variables={VISION_AGENT_API_KEY=${API_KEY},BUCKET_NAME=${BUCKET_NAME}} \
  --region ${AWS_REGION} \
  --profile ${AWS_PROFILE}

# Or update if it exists:
aws lambda update-function-code \
  --function-name ${FUNCTION_NAME} \
  --image-uri ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${FUNCTION_NAME}:latest \
  --region ${AWS_REGION} \
  --profile ${AWS_PROFILE}
```





##  Output Examples

### Batch Processing with Progress Bar

```
📋 Batch Invoice Extraction Test
================================================================================
   Found 11 PDF files to process
   ⏱️  Estimated time: 1-2 minutes

🚀 Invoking Lambda for batch processing...
   ⣾ Processing: [████████████░░░░░░░░░░░░░░░░░] 40% - 00:48

⏱️  Lambda returned after 119.3 seconds

✅ Batch processing successful!
   Documents processed: 11
   Average time per document: 10.8s
   Results location: s3://bucket/ade-results/batch_20250924.json

📊 Invoice Extraction Summary:
================================================================================
File         Invoice #    Date        Customer              Total      Items
invoice_1    INV33543191  2020-07-29  Abaxys Tech LLC      $149.90    1
invoice_2    2071221      2021-08-30  Souhail Martesse     $1,800.87  1
invoice_3    0000329003  2019-04-04  Nazish               ₹147.00    1
================================================================================

📈 Summary Statistics:
   Total invoices: 11
   Successfully extracted: 11
   Total value: $9,854.34
   
💾 Results exported to: extraction_results_20250924_125832.csv
```


### Lambda Configuration
- **Runtime**: Python 3.11 (Container)
- **Memory**: 1024 MB
- **Timeout**: 300 seconds (5 minutes) - configurable up to 900 seconds (15 minutes)
- **Architecture**: x86_64
- **Required Permissions**: S3 read/write, CloudWatch logs
- **Client Timeout**: 900 seconds (15 minutes) - prevents timeout errors for large batches

## 📈 Monitoring & Debugging

### View Lambda Logs
```bash
# Real-time logs
aws logs tail /aws/lambda/ade-lambda-s3 --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/ade-lambda-s3 \
  --filter-pattern ERROR
```

### Test Lambda Function
```bash
# Invoke test
aws lambda invoke \
  --function-name ade-lambda-s3 \
  --payload '{"bucket_name":"my-bucket","prefix":"test.pdf"}' \
  response.json

# Check response
cat response.json | jq
```

## 🆕 Custom Extraction Schemas

Add custom schemas in the schema section`utils.py`:

```python
from pydantic import BaseModel, Field
from typing import Optional, List

class ContractSchema(BaseModel):
    """Contract extraction schema."""
    contract_number: Optional[str] = Field(description="Contract ID")
    parties: List[str] = Field(description="Contracting parties")
    effective_date: Optional[str] = Field(description="Start date")
    total_value: Optional[float] = Field(description="Contract value")
    
# Register in EXTRACTION_SCHEMAS
EXTRACTION_SCHEMAS = {
    'invoice': InvoiceSchema,
    'contract': ContractSchema,  # New schema
    'receipt': ReceiptSchema,
    'purchase_order': PurchaseOrderSchema
}
```

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Timeout Error** | Lambda client configured with 15-minute timeout (max) to handle large batches |
| **Authentication** | Check AWS_PROFILE in .env file |
| **API Key Error** | Verify VISION_AGENT_API_KEY in .env |
| **No results** | Check CloudWatch logs for errors |
| **Docker build fails** | Ensure Docker daemon is running |
| **Config not loading** | Ensure .env file exists and is properly formatted |

## 📚 API Documentation

- **LandingAI ADE**: [docs.landing.ai/ade](https://docs.landing.ai/ade)
- **API Key**: [Get your key](https://docs.landing.ai/ade/agentic-api-key)
- **AWS Lambda**: [AWS Lambda docs](https://docs.aws.amazon.com/lambda/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📜 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- [LandingAI](https://landing.ai) for the ADE API
- AWS Lambda team for serverless compute
- Community contributors

---

**Built with ❤️ using LandingAI ADE and AWS Lambda**
