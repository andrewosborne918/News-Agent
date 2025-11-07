#!/usr/bin/env bash
set -euo pipefail

# Deploy Cloud Function and grant IAM for secrets and bucket access
# Usage:
#   bash scripts/deploy_cf.sh news-automation-477419 us-central1 news-videos-1762459809

PROJECT_ID=${1:-news-automation-477419}
REGION=${2:-us-central1}
BUCKET=${3:-news-videos-1762459809}

echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "Bucket:  $BUCKET"

pushd "$(dirname "$0")/.." >/dev/null

gcloud functions deploy gcs_to_social \
  --gen2 \
  --runtime=python311 \
  --source=./uploader \
  --region="$REGION" \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=$BUCKET" \
  --entry-point=gcs_to_social \
  --memory=512MB \
  --timeout=540s \
  --set-env-vars=GCP_PROJECT="$PROJECT_ID" \
  --project="$PROJECT_ID"

SA=$(gcloud functions describe gcs_to_social --region="$REGION" --gen2 --project="$PROJECT_ID" \
     --format='value(serviceConfig.serviceAccountEmail)')

echo "Function service account: $SA"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"

gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member="serviceAccount:$SA" \
  --role="roles/storage.objectViewer"

echo "✅ Deploy complete. Review logs with:"
echo "   gcloud functions logs read gcs_to_social --region=$REGION --gen2 --limit=50 --project=$PROJECT_ID"

popd >/dev/null
