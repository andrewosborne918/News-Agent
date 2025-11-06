#!/bin/bash
# GCP Setup Commands - Run these in Google Cloud Shell
# Copy and paste each section one at a time

echo "============================================================"
echo "GCP News Automation Setup"
echo "============================================================"
echo ""
echo "IMPORTANT: Run these commands in Google Cloud Shell"
echo "(Click the terminal icon in the top-right of GCP console)"
echo ""
echo "============================================================"
echo "STEP 1: Set Project and Enable APIs"
echo "============================================================"
echo ""
echo "Run this command:"
echo ""

cat << 'COMMANDS'
gcloud config set project news-automation

gcloud services enable \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  youtube.googleapis.com

echo "✅ APIs enabled!"
COMMANDS

echo ""
echo "============================================================"
echo "STEP 2: Create Storage Bucket"
echo "============================================================"
echo ""
echo "Run these commands:"
echo ""

cat << 'COMMANDS'
# Create a unique bucket name
export BUCKET=news-videos-$(date +%s)
gsutil mb -l us-central1 gs://$BUCKET

# Display the bucket name (SAVE THIS!)
echo ""
echo "============================================================"
echo "✅ Bucket created: $BUCKET"
echo "============================================================"
echo "IMPORTANT: Save this bucket name for GitHub secrets!"
echo ""
COMMANDS

echo ""
echo "============================================================"
echo "STEP 3: Create Service Account for GitHub"
echo "============================================================"
echo ""
echo "Run these commands:"
echo ""

cat << 'COMMANDS'
# Create service account
gcloud iam service-accounts create gh-actions-uploader \
  --display-name="GitHub Actions Uploader"

# Grant storage permissions
gcloud projects add-iam-policy-binding news-automation \
  --member="serviceAccount:gh-actions-uploader@news-automation.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"

# Create JSON key file
gcloud iam service-accounts keys create ~/gh-actions.json \
  --iam-account=gh-actions-uploader@news-automation.iam.gserviceaccount.com

echo ""
echo "✅ Service account created!"
echo ""
echo "============================================================"
echo "GitHub Secrets - ADD THESE TO YOUR GITHUB REPO:"
echo "============================================================"
echo "Go to: https://github.com/andrewosborne918/News-Agent/settings/secrets/actions"
echo ""
echo "Add these three secrets:"
echo ""
echo "1. GCP_PROJECT_ID"
echo "   Value: news-automation"
echo ""
echo "2. GCS_BUCKET"
echo "   Value: [your bucket name from Step 2]"
echo ""
echo "3. GCP_SA_KEY"
echo "   Value: [entire contents of file below]"
echo ""
echo "------------------------------------------------------------"
cat ~/gh-actions.json
echo ""
echo "------------------------------------------------------------"
echo ""
echo "Copy the JSON above (entire thing) and paste as GCP_SA_KEY"
echo "============================================================"
COMMANDS

echo ""
echo "============================================================"
echo "After completing these steps, continue to YouTube OAuth setup"
echo "See: get_youtube_token.py (run on your local computer)"
echo "============================================================"
