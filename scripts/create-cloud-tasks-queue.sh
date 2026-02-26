#!/bin/bash
# Create Cloud Tasks queue for preview deployments.
# Run with: ./scripts/create-cloud-tasks-queue.sh [PROJECT_ID] [LOCATION]
#
# Retry policy: exponential backoff (10s-300s), max 5 attempts, 1h total.
# Note: Cloud Tasks does not have built-in DLQ. After max_attempts, tasks are deleted.
# For DLQ-style handling, use a Dead Letter Topic (Cloud Tasks v2 beta) or monitor
# failed tasks via logging/alerting.

set -e

PROJECT_ID="${1:-${CLOUD_TASKS_PROJECT:-${GOOGLE_CLOUD_PROJECT}}}"
LOCATION="${2:-${CLOUD_TASKS_LOCATION:-us-central1}}"
QUEUE_NAME="${CLOUD_TASKS_QUEUE:-preview-deploy-queue}"

if [ -z "$PROJECT_ID" ]; then
  echo "Usage: $0 PROJECT_ID [LOCATION]"
  echo "  Or set CLOUD_TASKS_PROJECT / GOOGLE_CLOUD_PROJECT"
  exit 1
fi

echo "Creating queue: projects/$PROJECT_ID/locations/$LOCATION/queues/$QUEUE_NAME"

gcloud tasks queues create "$QUEUE_NAME" \
  --location="$LOCATION" \
  --project="$PROJECT_ID" \
  --max-dispatches-per-second=10 \
  --max-concurrent-dispatches=50 \
  --min-backoff=10s \
  --max-backoff=300s \
  --max-attempts=5 \
  --max-retry-duration=3600s

echo "Queue created. Configure these env vars in GitHub App and Deployer:"
echo "  CLOUD_TASKS_PROJECT=$PROJECT_ID"
echo "  CLOUD_TASKS_LOCATION=$LOCATION"
echo "  CLOUD_TASKS_QUEUE=$QUEUE_NAME"
