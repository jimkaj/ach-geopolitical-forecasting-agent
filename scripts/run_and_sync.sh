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

# Commit and push regenerated matrix output so GitHub Pages picks it up
git config user.name "ACH Pipeline Bot"
git config user.email "acch-pipeline@users.noreply.github.com"
git add data/matrix
if ! git diff --cached --quiet; then
  git commit -m "Auto-update ACH matrix output: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push origin master
else
  echo "No matrix changes to commit"
fi

echo "=== Pipeline complete: $(date -u) ==="

# Shut down EC2 to stop billing
sudo shutdown -h now
