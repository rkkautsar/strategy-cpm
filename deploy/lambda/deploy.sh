#!/usr/bin/env bash
# One-shot Lambda deployment.
#
# Prereqs (one-time):
#   1. aws configure   (sets ~/.aws/credentials)
#   2. Docker running
#   3. Telegram bot created (token + chat_id ready)
#
# Usage:
#   export TELEGRAM_BOT_TOKEN=<your-token>
#   export TELEGRAM_CHAT_ID=<your-chat-id>
#   ./deploy/lambda/deploy.sh
#
# Re-run safely: idempotent. Updates existing function/schedule if present.

set -euo pipefail

# === Config (edit if needed) ===
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO="${ECR_REPO:-cpm-bull-signal}"
LAMBDA_NAME="${LAMBDA_NAME:-cpm-bull-signal}"
LAMBDA_ROLE="${LAMBDA_ROLE:-lambda-basic-execution}"
SCHEDULE_NAME="${SCHEDULE_NAME:-cpm-bull-monthly}"
# Cron: 1st of month at 14:00 UTC (= 10am ET standard / 9am ET DST)
SCHEDULE_CRON="${SCHEDULE_CRON:-cron(0 14 1 * ? *)}"
LAMBDA_TIMEOUT="${LAMBDA_TIMEOUT:-120}"
LAMBDA_MEMORY="${LAMBDA_MEMORY:-512}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# === Validate prereqs ===
echo "==> Validating prereqs"
command -v aws >/dev/null || { echo "ERROR: aws CLI not installed"; exit 1; }
command -v docker >/dev/null || { echo "ERROR: docker not installed"; exit 1; }
docker info >/dev/null 2>&1 || { echo "ERROR: Docker daemon not running"; exit 1; }
aws sts get-caller-identity >/dev/null 2>&1 || { echo "ERROR: aws not configured (run: aws configure)"; exit 1; }
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] || { echo "ERROR: TELEGRAM_BOT_TOKEN not set"; exit 1; }
[ -n "${TELEGRAM_CHAT_ID:-}" ] || { echo "ERROR: TELEGRAM_CHAT_ID not set"; exit 1; }
echo "    OK"

# === Derived values ===
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

echo ""
echo "==> Deployment target"
echo "    Account:   $AWS_ACCOUNT_ID"
echo "    Region:    $AWS_REGION"
echo "    ECR:       $ECR_URI"
echo "    Lambda:    $LAMBDA_NAME"
echo "    Schedule:  $SCHEDULE_NAME ($SCHEDULE_CRON)"
echo ""

# === Step 1: IAM role for Lambda ===
echo "==> [1/6] Ensuring IAM role $LAMBDA_ROLE"
if ! aws iam get-role --role-name "$LAMBDA_ROLE" >/dev/null 2>&1; then
    echo "    Creating role..."
    aws iam create-role --role-name "$LAMBDA_ROLE" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
        }' >/dev/null
    aws iam attach-role-policy --role-name "$LAMBDA_ROLE" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    echo "    Created. Waiting 10s for IAM propagation..."
    sleep 10
fi
ROLE_ARN="$(aws iam get-role --role-name "$LAMBDA_ROLE" --query 'Role.Arn' --output text)"
echo "    Role ARN: $ROLE_ARN"

# === Step 2: ECR repo ===
echo ""
echo "==> [2/6] Ensuring ECR repo $ECR_REPO"
if ! aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1; then
    aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" >/dev/null
    echo "    Created"
fi

# === Step 3: Build + push image ===
echo ""
echo "==> [3/6] Building + pushing container image"
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com" 2>&1 | grep -v "^WARNING" || true

docker build --platform linux/amd64 \
    -f deploy/lambda/Dockerfile \
    -t "${ECR_REPO}:${IMAGE_TAG}" .
docker tag "${ECR_REPO}:${IMAGE_TAG}" "$IMAGE_URI"
docker push "$IMAGE_URI"
echo "    Image: $IMAGE_URI"

# === Step 4: Lambda function (create or update) ===
echo ""
echo "==> [4/6] Deploying Lambda function $LAMBDA_NAME"
if aws lambda get-function --function-name "$LAMBDA_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "    Function exists, updating code + config..."
    aws lambda update-function-code \
        --function-name "$LAMBDA_NAME" \
        --image-uri "$IMAGE_URI" \
        --region "$AWS_REGION" \
        --no-cli-pager >/dev/null
    # Wait for code update to settle
    aws lambda wait function-updated --function-name "$LAMBDA_NAME" --region "$AWS_REGION"
    aws lambda update-function-configuration \
        --function-name "$LAMBDA_NAME" \
        --timeout "$LAMBDA_TIMEOUT" \
        --memory-size "$LAMBDA_MEMORY" \
        --environment "Variables={TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID}" \
        --region "$AWS_REGION" \
        --no-cli-pager >/dev/null
else
    echo "    Creating function..."
    aws lambda create-function \
        --function-name "$LAMBDA_NAME" \
        --package-type Image \
        --code "ImageUri=$IMAGE_URI" \
        --role "$ROLE_ARN" \
        --timeout "$LAMBDA_TIMEOUT" \
        --memory-size "$LAMBDA_MEMORY" \
        --environment "Variables={TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID}" \
        --region "$AWS_REGION" \
        --no-cli-pager >/dev/null
fi
LAMBDA_ARN="$(aws lambda get-function --function-name "$LAMBDA_NAME" --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text)"
echo "    Lambda ARN: $LAMBDA_ARN"

# === Step 5: EventBridge schedule ===
echo ""
echo "==> [5/6] Setting up EventBridge schedule $SCHEDULE_NAME"
aws events put-rule \
    --name "$SCHEDULE_NAME" \
    --schedule-expression "$SCHEDULE_CRON" \
    --state ENABLED \
    --region "$AWS_REGION" \
    --no-cli-pager >/dev/null
RULE_ARN="$(aws events describe-rule --name "$SCHEDULE_NAME" --region "$AWS_REGION" --query 'Arn' --output text)"
echo "    Rule ARN: $RULE_ARN"

aws events put-targets \
    --rule "$SCHEDULE_NAME" \
    --targets "Id=1,Arn=$LAMBDA_ARN" \
    --region "$AWS_REGION" \
    --no-cli-pager >/dev/null

# Allow EventBridge to invoke Lambda (ignore error if permission exists)
aws lambda add-permission \
    --function-name "$LAMBDA_NAME" \
    --statement-id allow-eventbridge \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "$RULE_ARN" \
    --region "$AWS_REGION" \
    --no-cli-pager >/dev/null 2>&1 || echo "    (permission already exists)"

# === Step 6: Test invocation ===
echo ""
echo "==> [6/6] Test invocation"
echo "    Invoking Lambda with empty payload..."
aws lambda invoke \
    --function-name "$LAMBDA_NAME" \
    --payload '{}' \
    --cli-binary-format raw-in-base64-out \
    --region "$AWS_REGION" \
    --no-cli-pager \
    /tmp/lambda_test_output.json >/dev/null

echo "    Response:"
cat /tmp/lambda_test_output.json | python3 -m json.tool 2>/dev/null || cat /tmp/lambda_test_output.json
echo ""
echo ""
echo "✅ DEPLOYMENT COMPLETE"
echo ""
echo "Check your Telegram for the test message."
echo ""
echo "Schedule will fire monthly: $SCHEDULE_CRON"
echo "  = 1st of each month at 14:00 UTC (10am ET / 9am ET DST)"
echo ""
echo "Useful commands:"
echo "  Logs:    aws logs tail /aws/lambda/$LAMBDA_NAME --follow --region $AWS_REGION"
echo "  Invoke:  aws lambda invoke --function-name $LAMBDA_NAME /tmp/out.json --region $AWS_REGION && cat /tmp/out.json"
echo "  Update:  ./deploy/lambda/deploy.sh    (re-run to deploy new code)"
echo "  Pause:   aws events disable-rule --name $SCHEDULE_NAME --region $AWS_REGION"
echo "  Resume:  aws events enable-rule --name $SCHEDULE_NAME --region $AWS_REGION"
echo "  Delete:  see deploy/lambda/teardown.sh"
