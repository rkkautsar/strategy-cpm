#!/usr/bin/env bash
# Delete everything created by deploy.sh.
# Usage: ./deploy/lambda/teardown.sh

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO="${ECR_REPO:-fcp-bull-signal}"
LAMBDA_NAME="${LAMBDA_NAME:-fcp-bull-signal}"
LAMBDA_ROLE="${LAMBDA_ROLE:-lambda-basic-execution}"
SCHEDULE_NAME="${SCHEDULE_NAME:-fcp-bull-monthly}"

echo "==> Tearing down FCP+BULL Lambda deployment"
echo "    Region: $AWS_REGION"
echo "    Lambda: $LAMBDA_NAME"
echo ""
read -p "Are you sure? Type 'yes' to confirm: " confirm
[ "$confirm" = "yes" ] || { echo "Aborted."; exit 1; }

# Schedule
aws events remove-targets --rule "$SCHEDULE_NAME" --ids 1 --region "$AWS_REGION" 2>/dev/null || true
aws events delete-rule --name "$SCHEDULE_NAME" --region "$AWS_REGION" 2>/dev/null || true
echo "    Schedule removed"

# Lambda
aws lambda delete-function --function-name "$LAMBDA_NAME" --region "$AWS_REGION" 2>/dev/null || true
echo "    Lambda removed"

# ECR (keeps repo, deletes images)
aws ecr batch-delete-image --repository-name "$ECR_REPO" --region "$AWS_REGION" \
    --image-ids "$(aws ecr list-images --repository-name "$ECR_REPO" --region "$AWS_REGION" --query 'imageIds' --output json)" 2>/dev/null || true
aws ecr delete-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" --force 2>/dev/null || true
echo "    ECR repo removed"

# Role (keep by default — might be shared with other Lambdas)
echo ""
echo "    IAM role $LAMBDA_ROLE preserved (may be shared)."
echo "    To delete manually: aws iam detach-role-policy --role-name $LAMBDA_ROLE --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole && aws iam delete-role --role-name $LAMBDA_ROLE"
echo ""
echo "Done."
