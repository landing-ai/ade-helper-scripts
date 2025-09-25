#!/bin/bash

# Build and push Docker image to ECR for ADE Lambda
# This script reads configuration from .env file or environment variables

set -e

# Load configuration from Settings (reads .env or environment)
echo "📋 Loading configuration from Settings..."
AWS_PROFILE=$(python3 -c "from config import get_settings; s=get_settings(); print(s.aws_profile)" 2>/dev/null || echo "default")
AWS_REGION=$(python3 -c "from config import get_settings; s=get_settings(); print(s.aws_region)" 2>/dev/null || echo "us-east-2")
AWS_ACCOUNT_ID=$(python3 -c "from config import get_settings; s=get_settings(); print(s.aws_account_id or '')" 2>/dev/null || echo "")
ECR_REPO=$(python3 -c "from config import get_settings; s=get_settings(); print(s.ecr_repo)" 2>/dev/null || echo "ade-lambda-s3")

# Show loaded configuration
echo "   Profile: ${AWS_PROFILE}"
echo "   Region: ${AWS_REGION}"
echo "   ECR Repo: ${ECR_REPO}"

# Export for AWS CLI
export AWS_PROFILE
export AWS_REGION

IMAGE_TAG="latest"

# Parse command line arguments
NO_CACHE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cache)
            NO_CACHE="--no-cache"
            echo "🔄 Force rebuild enabled (--no-cache)"
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--no-cache]"
            echo "  --no-cache  Force rebuild without using Docker cache"
            exit 1
            ;;
    esac
    shift
done

# Get AWS Account ID if not provided
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "🔍 Getting AWS Account ID..."
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile ${AWS_PROFILE})
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        echo "❌ Error: Could not get AWS Account ID. Please check your AWS credentials."
        exit 1
    fi
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"

echo ""
echo "🐳 Docker Build Configuration:"
echo "================================"
echo "   AWS Profile: ${AWS_PROFILE}"
echo "   AWS Region: ${AWS_REGION}"
echo "   AWS Account: ${AWS_ACCOUNT_ID}"
echo "   ECR Repository: ${ECR_REPO}"
echo "   Image URI: ${FULL_IMAGE_URI}"
echo "================================"
echo ""

# Check required files exist
echo "✅ Checking required files..."
for file in handler.py config.py Dockerfile requirements.txt; do
    if [ ! -f "$file" ]; then
        echo "❌ Error: Required file '$file' not found"
        exit 1
    fi
    echo "   ✓ $file"
done
echo ""

# Step 1: Authenticate Docker to ECR
echo "🔐 Step 1: Authenticating Docker to ECR..."
aws ecr get-login-password --region ${AWS_REGION} --profile ${AWS_PROFILE} | \
    docker login --username AWS --password-stdin ${ECR_REGISTRY}

if [ $? -ne 0 ]; then
    echo "❌ Failed to authenticate Docker to ECR"
    exit 1
fi
echo "   ✓ Login Succeeded"
echo ""

# Step 2: Create ECR repository if it doesn't exist
echo "📦 Step 2: Creating ECR repository (if needed)..."
aws ecr describe-repositories --repository-names ${ECR_REPO} \
    --region ${AWS_REGION} --profile ${AWS_PROFILE} 2>/dev/null || \
    aws ecr create-repository --repository-name ${ECR_REPO} \
        --region ${AWS_REGION} --profile ${AWS_PROFILE}

if [ $? -eq 0 ]; then
    echo "   ✓ Repository ready: ${ECR_REPO}"
else
    echo "   ✓ Repository already exists: ${ECR_REPO}"
fi
echo ""

# Step 3: Build and push Docker image
echo "🔨 Step 3: Building and pushing Docker image..."
if [ -n "$NO_CACHE" ]; then
    echo "   🔄 Building WITHOUT cache (fresh rebuild)"
    echo "   ⏱️  This will take 3-5 minutes..."
else
    echo "   📦 Building WITH cache (faster if unchanged)"
    echo "   ⏱️  This will take 1-3 minutes..."
    echo "   💡 Tip: Use './build.sh --no-cache' to force a fresh rebuild"
fi
echo ""

# Build for ARM64 without buildx to avoid multi-arch manifest issues
echo "   Building Docker image for ARM64 architecture..."
echo "   Note: Using standard docker build to ensure Lambda compatibility"
# Disable buildkit to avoid OCI manifest issues
export DOCKER_BUILDKIT=0
docker build --platform linux/arm64 ${NO_CACHE} -t ${FULL_IMAGE_URI} .

# Push the image
echo "   Pushing image to ECR..."
docker push ${FULL_IMAGE_URI}

if [ $? -ne 0 ]; then
    echo "❌ Failed to build or push Docker image"
    exit 1
fi

echo ""
echo "✅ Success! Docker image pushed to ECR"
echo "================================"
echo "   Image URI: ${FULL_IMAGE_URI}"
echo "================================"
echo ""

# Verify the image was pushed
echo "🔍 Verifying image in ECR..."
aws ecr describe-images --repository-name ${ECR_REPO} \
    --region ${AWS_REGION} --profile ${AWS_PROFILE} \
    --query 'imageDetails[?imageTags[?contains(@, `latest`)]].{Tags:imageTags,Size:imageSizeInBytes,Pushed:imagePushedAt}' \
    --output table

echo ""
echo "📝 Next Steps:"
echo "   1. Return to the Jupyter notebook"
echo "   2. Run the 'Deploy Lambda Function' cell"
echo "   3. The Lambda will use this image: ${FULL_IMAGE_URI}"
echo ""
echo "✨ Docker build complete!"