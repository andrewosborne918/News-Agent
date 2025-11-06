#!/bin/bash
# Deploy the Cloud Function to Google Cloud Platform
# Run this from the project root directory

set -e

echo "============================================================"
echo "Deploying Cloud Function"
echo "============================================================"

# Check if we're in the right directory
if [ ! -d "uploader" ]; then
    echo "❌ Error: uploader/ directory not found"
    echo "Run this script from the project root"
    exit 1
fi

# Get configuration
read -p "Enter your GCP Project ID: " PROJECT_ID
read -p "Enter your GCS Bucket name: " BUCKET

gcloud config set project $PROJECT_ID

echo ""
echo "Deploying function..."
echo "This may take 3-5 minutes..."

cd uploader/

gcloud functions deploy gcs_to_social \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=$BUCKET" \
  --entry-point=gcs_to_social \
  --memory=512MB \
  --timeout=540s \
  --set-env-vars=GCP_PROJECT=$PROJECT_ID

cd ..

echo ""
echo "============================================================"
echo "Granting Secret Manager access..."
echo "============================================================"

SA=$(gcloud functions describe gcs_to_social --region=us-central1 --gen2 --format='value(serviceConfig.serviceAccountEmail)')

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"

echo ""
echo "============================================================"
echo "✅ Deployment complete!"
echo "============================================================"
echo ""
echo "Test the function:"
echo "  gsutil cp test-video.mp4 gs://$BUCKET/incoming/"
echo ""
echo "View logs:"
echo "  gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50"
echo ""
