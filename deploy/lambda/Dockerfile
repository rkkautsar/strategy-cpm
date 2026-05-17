# AWS Lambda container image: FCP+BULL monthly signal -> Telegram
# Build:    docker build --platform linux/amd64 -t fcp-signal:latest .
# Test:     docker run --rm -e DRY_RUN=true fcp-signal:latest
# Push:     see build_and_push.sh

FROM public.ecr.aws/lambda/python:3.13

# Install OS packages needed by scientific stack
RUN dnf install -y gcc && dnf clean all

# Copy requirements first for layer caching
COPY deploy/lambda/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -t /var/task

# Bundle strategy modules under /var/task (Lambda's working dir)
COPY fcp_live.py            /var/task/
COPY bull_qqq_live.py       /var/task/
COPY data/                  /var/task/data/
COPY deploy/lambda/handler.py /var/task/

# Lambda entrypoint: <module>.<function>
CMD ["handler.lambda_handler"]
