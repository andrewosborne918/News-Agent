#!/bin/bash
# Quick setup script for Google Cloud Platform
# Run this in Google Cloud Shell or local terminal with gcloud installed

set -e  # Exit on error

echo "============================================================"
echo "GCP News Automation Setup"
echo "============================================================"

# Get project ID
read -p "Enter your GCP Project ID: " PROJECT_ID
gcloud config set project $PROJECT_ID

echo ""
echo "============================================================"
echo "Step 1: Enabling APIs..."
echo "============================================================"

gcloud services enable \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  youtube.googleapis.com

echo "✅ APIs enabled"

echo ""
echo "============================================================"
echo "Step 2: Creating Storage Bucket..."
echo "============================================================"

BUCKET="news-videos-$RANDOM"
gsutil mb -l us-central1 gs://$BUCKET

echo "✅ Bucket created: gs://$BUCKET"
echo "SAVE THIS: GCS_BUCKET=$BUCKET"

echo ""
echo "============================================================"
echo "Step 3: Creating Service Account for GitHub..."
echo "============================================================"

gcloud iam service-accounts create gh-actions-uploader \
  --display-name="GitHub Actions Uploader"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:gh-actions-uploader@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"

gcloud iam service-accounts keys create gh-actions.json \
  --iam-account=gh-actions-uploader@$PROJECT_ID.iam.gserviceaccount.com

echo "✅ Service account created"
echo ""
echo "============================================================"
echo "GitHub Secrets to Add:"
echo "============================================================"
echo "GCP_PROJECT_ID: $PROJECT_ID"
echo "GCS_BUCKET: $BUCKET"
echo "GCP_SA_KEY: (contents of gh-actions.json below)"
echo "============================================================"
cat gh-actions.json
echo "============================================================"

echo ""
echo "✅ GCP setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy the secrets above to GitHub (Settings → Secrets → Actions)"
echo "2. Get YouTube OAuth token (run get_youtube_token.py locally)"
echo "3. Get Facebook Page token (see GCP_SETUP_GUIDE.md Part 3)"
echo "4. Store secrets in Secret Manager"
echo "5. Deploy Cloud Function"
echo ""
echo "See GCP_SETUP_GUIDE.md for detailed instructions"
