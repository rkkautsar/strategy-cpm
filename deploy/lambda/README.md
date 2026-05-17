# AWS Lambda monthly signal deployment

Runs the CPM-BULL strategy on the 1st of each month, sends the signal to
your Telegram chat. Free at this volume (~$0/year on Lambda + EventBridge).

## Quick start (one-time setup, ~1 hour)

### 1. Create Telegram bot (~5 min)

1. Open Telegram, message `@BotFather`
2. `/newbot` → pick a name and username → save the **bot token**
3. Message your new bot once (any text)
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → find your **chat_id** (number)

### 2. AWS setup (~10 min)

```bash
# Install + configure AWS CLI if needed
brew install awscli
aws configure  # provide your access key, secret, region (e.g. us-east-1)

# Verify access
aws sts get-caller-identity
```

### 3. Build + push container (~20 min, mostly download)

From `strategy_cpm/` root:

```bash
chmod +x deploy/lambda/build_and_push.sh
./deploy/lambda/build_and_push.sh
```

Output ends with the image URI:
`123456789.dkr.ecr.us-east-1.amazonaws.com/cpm-bull-signal:latest`

### 4. Create Lambda function (~10 min)

```bash
# Replace IMAGE_URI with output from step 3
IMAGE_URI="123456789.dkr.ecr.us-east-1.amazonaws.com/cpm-bull-signal:latest"
ROLE_ARN="arn:aws:iam::123456789:role/lambda-basic-execution"  # create if missing

# Create role first if you don't have one:
aws iam create-role --role-name lambda-basic-execution \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    }'
aws iam attach-role-policy --role-name lambda-basic-execution \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create the function (use ROLE_ARN from above)
aws lambda create-function \
    --function-name cpm-bull-signal \
    --package-type Image \
    --code ImageUri=$IMAGE_URI \
    --role $ROLE_ARN \
    --timeout 60 \
    --memory-size 512 \
    --environment "Variables={TELEGRAM_BOT_TOKEN=<paste-token>,TELEGRAM_CHAT_ID=<paste-chat-id>}"
```

Test it:

```bash
aws lambda invoke --function-name cpm-bull-signal --payload '{}' /tmp/out.json
cat /tmp/out.json
# You should receive a Telegram message
```

### 5. Schedule it monthly (~5 min)

```bash
# Create EventBridge schedule (1st of each month at 14:00 UTC = 10am ET)
aws events put-rule \
    --name cpm-bull-monthly \
    --schedule-expression 'cron(0 14 1 * ? *)' \
    --state ENABLED

# Get the Lambda ARN
LAMBDA_ARN=$(aws lambda get-function --function-name cpm-bull-signal --query 'Configuration.FunctionArn' --output text)

# Wire EventBridge -> Lambda
aws events put-targets --rule cpm-bull-monthly \
    --targets "Id"="1","Arn"="$LAMBDA_ARN"

# Allow EventBridge to invoke Lambda
aws lambda add-permission \
    --function-name cpm-bull-signal \
    --statement-id allow-eventbridge \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn $(aws events describe-rule --name cpm-bull-monthly --query 'Arn' --output text)
```

Done. You'll receive a Telegram message on the 1st of each month at 10am ET.

## Updates

Whenever you change strategy code:

```bash
./deploy/lambda/build_and_push.sh
aws lambda update-function-code \
    --function-name cpm-bull-signal \
    --image-uri $IMAGE_URI
```

## Local testing

```bash
# Set env vars
export TELEGRAM_BOT_TOKEN=<your-token>
export TELEGRAM_CHAT_ID=<your-chat-id>
export DRY_RUN=true  # log signal without sending

cd strategy_fcp
uv run python deploy/lambda/handler.py
```

## Cost

- Lambda: 12 invocations/year × ~30s × 512MB = ~$0.0001/year (free tier covers it)
- EventBridge: free for scheduled rules
- ECR: ~250MB image × $0.10/GB/month = ~$0.30/year (free 500MB/month tier covers it)
- **Total: ~$0/year**

## Troubleshooting

| Issue | Fix |
|---|---|
| "Image not found" on Lambda create | Wait 1-2 min after push, ECR propagation |
| Timeout in Lambda | Increase --timeout to 120 (yfinance can be slow) |
| "Cannot find package pandas" | Rebuild image; requirements.txt missing or platform mismatch |
| No Telegram message arrived | Check CloudWatch logs (`aws logs tail /aws/lambda/cpm-bull-signal --follow`) |
| Schedule not firing | Verify rule is ENABLED and Lambda permission is added |

## Files

```
deploy/lambda/
├── README.md            -- this file
├── Dockerfile           -- Lambda container image
├── requirements.txt     -- Python deps for Lambda
├── handler.py           -- Lambda entrypoint, computes signal, sends to Telegram
└── build_and_push.sh    -- Build, tag, push to ECR
```
