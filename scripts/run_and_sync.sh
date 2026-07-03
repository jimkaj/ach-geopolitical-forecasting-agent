#!/bin/bash
set -euo pipefail
exec >> /home/ubuntu/pipeline.log 2>&1

echo "=== Pipeline start: $(date -u) ==="

cd /home/ubuntu/CMU_Project

# Pull latest code
git pull origin master

# Inject Guardian API key from Secrets Manager
export GUARDIAN_API_KEY=$(aws secretsmanager get-secret-value \
    --secret-id acch/guardian-api-key \
    --query SecretString \
    --output text \
    --region us-east-1)

# Run the pipeline
uv run python main.py

# Sync HTML outputs to S3 (replace BUCKET_NAME with your actual bucket)
aws s3 sync data/matrix/ s3://BUCKET_NAME/ \
    --delete \
    --cache-control "max-age=3600" \
    --region us-east-1

echo "=== Pipeline complete: $(date -u) ==="

# Shut down EC2 to stop billing
sudo shutdown -h now
