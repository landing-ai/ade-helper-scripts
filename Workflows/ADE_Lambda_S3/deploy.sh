#!/bin/bash

# Deploy Lambda function from ECR image
# This script reads configuration from .env file or environment variables

set -e

# Load configuration from Settings (reads .env or environment)
echo "📋 Loading configuration from Settings..."
AWS_PROFILE=$(python3 -c "from config import get_settings; s=get_settings(); print(s.aws_profile)" 2>/dev/null || echo "default")
AWS_REGION=$(python3 -c "from config import get_settings; s=get_settings(); print(s.aws_region)" 2>/dev/null || echo "us-east-2")
AWS_ACCOUNT_ID=$(python3 -c "from config import get_settings; s=get_settings(); print(s.aws_account_id or '')" 2>/dev/null || echo "")
BUCKET_NAME=$(python3 -c "from config import get_settings; s=get_settings(); print(s.bucket_name)" 2>/dev/null || echo "")
FUNCTION_NAME=$(python3 -c "from config import get_settings; s=get_settings(); print(s.function_name)" 2>/dev/null || echo "ade-lambda-s3")
ECR_REPO=$(python3 -c "from config import get_settings; s=get_settings(); print(s.ecr_repo)" 2>/dev/null || echo "ade-lambda-s3")
ROLE_NAME=$(python3 -c "from config import get_settings; s=get_settings(); print(s.role_name)" 2>/dev/null || echo "ade-lambda-s3-role")
VISION_AGENT_API_KEY=$(python3 -c "from config import get_settings; s=get_settings(); print(s.vision_agent_api_key)" 2>/dev/null || echo "")
TIMEOUT=$(python3 -c "from config import get_settings; s=get_settings(); print(s.timeout_seconds)" 2>/dev/null || echo "300")

# Show loaded configuration
echo "   Profile: ${AWS_PROFILE}"
echo "   Region: ${AWS_REGION}"
echo "   Function: ${FUNCTION_NAME}"
echo "   Bucket: ${BUCKET_NAME}"

# Export for AWS CLI
export AWS_PROFILE
export AWS_REGION

# Lambda configuration
MEMORY_SIZE=1024  # MB

# Get AWS Account ID if not provided
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "🔍 Getting AWS Account ID..."
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile ${AWS_PROFILE} 2>/dev/null)
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        echo "❌ Error: Could not get AWS Account ID. Please check your AWS credentials."
        exit 1
    fi
fi

# Check required configuration
if [ -z "$VISION_AGENT_API_KEY" ]; then
    echo "❌ Error: VISION_AGENT_API_KEY is not set in config.json"
    exit 1
fi

if [ -z "$BUCKET_NAME" ]; then
    echo "❌ Error: BUCKET_NAME is not set in config.json"
    exit 1
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG:-latest}"

echo ""
echo "🚀 Deploying Lambda Function"
echo "================================"
echo "   Function: ${FUNCTION_NAME}"
echo "   Image: ${FULL_IMAGE_URI}"
echo "   Region: ${AWS_REGION}"
echo "   Bucket: ${BUCKET_NAME}"
echo "================================"
echo ""

# Check if we can manage IAM roles
CAN_MANAGE_IAM=false
if aws iam list-roles --max-items 1 --profile ${AWS_PROFILE} 2>/dev/null >/dev/null; then
    CAN_MANAGE_IAM=true
    echo "✅ IAM permissions detected"
else
    echo "⚠️  No IAM permissions detected"
fi

ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"

if [ "$CAN_MANAGE_IAM" = true ]; then
    # Check if role exists
    if ! aws iam get-role --role-name ${ROLE_NAME} --profile ${AWS_PROFILE} 2>/dev/null; then
        echo "📝 Creating IAM role: ${ROLE_NAME}"
        
        # Create trust policy
        cat > /tmp/trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
        
        # Create the role
        aws iam create-role \
            --role-name ${ROLE_NAME} \
            --assume-role-policy-document file:///tmp/trust-policy.json \
            --profile ${AWS_PROFILE}
        
        # Attach basic Lambda execution policy
        aws iam attach-role-policy \
            --role-name ${ROLE_NAME} \
            --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
            --profile ${AWS_PROFILE}
        
        # Create and attach S3 policy
        cat > /tmp/s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ]
    }
  ]
}
EOF
        
        aws iam put-role-policy \
            --role-name ${ROLE_NAME} \
            --policy-name s3-access-policy \
            --policy-document file:///tmp/s3-policy.json \
            --profile ${AWS_PROFILE}
        
        echo "✅ Created IAM role with S3 permissions"
        echo "⏳ Waiting for IAM role to propagate..."
        sleep 10
    else
        echo "✅ Using existing IAM role: ${ROLE_NAME}"
    fi
else
    echo ""
    echo "⚠️  MANUAL SETUP REQUIRED:"
    echo "   Since you don't have IAM permissions, please ask an administrator to:"
    echo "   1. Create IAM role: ${ROLE_NAME}"
    echo "   2. Add trust relationship for Lambda service"
    echo "   3. Attach policies:"
    echo "      - AWSLambdaBasicExecutionRole"
    echo "      - S3 access for bucket: ${BUCKET_NAME}"
    echo ""
    echo "   Or provide an existing role ARN in config.json"
    echo ""
    
    if [ -z "$ROLE_ARN" ]; then
        echo "❌ Cannot proceed without IAM role"
        exit 1
    fi
fi

# Environment variables for Lambda (without AWS_REGION which is reserved)
# Create a temporary file for environment variables to avoid escaping issues
cat > /tmp/lambda-env-vars.json <<EOF
{
  "Variables": {
    "VISION_AGENT_API_KEY": "${VISION_AGENT_API_KEY}",
    "BUCKET_NAME": "${BUCKET_NAME}"
  }
}
EOF

# Check if Lambda function exists
if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${AWS_REGION} --profile ${AWS_PROFILE} 2>/dev/null; then
    echo "📝 Updating existing Lambda function..."
    
    # Update function code
    aws lambda update-function-code \
        --function-name ${FUNCTION_NAME} \
        --image-uri ${FULL_IMAGE_URI} \
        --region ${AWS_REGION} \
        --profile ${AWS_PROFILE}
    
    # Wait for update to complete
    echo "⏳ Waiting for function code update..."
    aws lambda wait function-updated \
        --function-name ${FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${AWS_PROFILE}
    
    # Update function configuration
    aws lambda update-function-configuration \
        --function-name ${FUNCTION_NAME} \
        --timeout ${TIMEOUT} \
        --memory-size ${MEMORY_SIZE} \
        --environment file:///tmp/lambda-env-vars.json \
        --region ${AWS_REGION} \
        --profile ${AWS_PROFILE}
    
    echo "⏳ Waiting for configuration update..."
    aws lambda wait function-updated \
        --function-name ${FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${AWS_PROFILE}
    
    echo "✅ Lambda function updated successfully!"
    
else
    echo "✨ Creating new Lambda function..."
    
    aws lambda create-function \
        --function-name ${FUNCTION_NAME} \
        --package-type Image \
        --code ImageUri=${FULL_IMAGE_URI} \
        --role ${ROLE_ARN} \
        --timeout ${TIMEOUT} \
        --memory-size ${MEMORY_SIZE} \
        --architectures arm64 \
        --environment file:///tmp/lambda-env-vars.json \
        --description "ADE document processor for S3" \
        --region ${AWS_REGION} \
        --profile ${AWS_PROFILE}
    
    echo "⏳ Waiting for function to become active..."
    aws lambda wait function-active \
        --function-name ${FUNCTION_NAME} \
        --region ${AWS_REGION} \
        --profile ${AWS_PROFILE}
    
    echo "✅ Lambda function created successfully!"
fi

# Add S3 invoke permission
echo "🔧 Adding S3 invoke permission..."
aws lambda add-permission \
    --function-name ${FUNCTION_NAME} \
    --statement-id s3-trigger-permission \
    --action lambda:InvokeFunction \
    --principal s3.amazonaws.com \
    --source-arn arn:aws:s3:::${BUCKET_NAME} \
    --region ${AWS_REGION} \
    --profile ${AWS_PROFILE} 2>/dev/null || echo "   Permission may already exist"

echo ""
echo "✅ Lambda Deployment Complete!"
echo "================================"
echo "   Function: ${FUNCTION_NAME}"
echo "   Region: ${AWS_REGION}"
echo "   ARN: arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${FUNCTION_NAME}"
echo ""
echo "📝 Next Steps:"
echo "   1. Test the function: ./test.sh"
echo "   2. View logs in CloudWatch"
echo "   3. Set up S3 triggers if needed"
echo ""

# Clean up temporary file
rm -f /tmp/lambda-env-vars.json