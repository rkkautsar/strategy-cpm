#!/usr/bin/env bash
# Build, tag, and push Lambda container image to AWS ECR.
#
# Prereqs:
#   - AWS CLI configured (aws configure)
#   - Docker running
#   - ECR repo created (this script creates it if missing)
#
# Usage:
#   cd strategy_fcp
#   ./deploy/lambda/build_and_push.sh

set -euo pipefail

# === Config (edit these) ===
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO="${ECR_REPO:-cpm-bull-signal}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# === Derived ===
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

echo "==> Region:        $AWS_REGION"
echo "==> Account ID:    $AWS_ACCOUNT_ID"
echo "==> ECR repo:      $ECR_REPO"
echo "==> Image URI:     ${ECR_URI}:${IMAGE_TAG}"
echo ""

# === Ensure ECR repo exists ===
if ! aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "==> Creating ECR repo $ECR_REPO"
    aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" >/dev/null
fi

# === Login to ECR ===
echo "==> Logging into ECR"
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# === Build (force amd64 for Lambda) ===
echo "==> Building image (linux/amd64)"
docker build --platform linux/amd64 \
    -f deploy/lambda/Dockerfile \
    -t "${ECR_REPO}:${IMAGE_TAG}" \
    .

# === Tag + push ===
echo "==> Pushing to ECR"
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

echo ""
echo "==> Done! Image URI:"
echo "    ${ECR_URI}:${IMAGE_TAG}"
echo ""
echo "Next: create/update Lambda to use this image."
echo "  Or run: aws lambda update-function-code \\"
echo "    --function-name cpm-bull-signal \\"
echo "    --image-uri ${ECR_URI}:${IMAGE_TAG} \\"
echo "    --region $AWS_REGION"
