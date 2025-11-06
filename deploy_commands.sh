#!/bin/bash
# Cloud Function Deployment Commands for GCP

echo "======================================"
echo "STEP 1: Deploy the Cloud Function"
echo "======================================"
echo ""
echo "Copy and paste this command into Cloud Shell:"
echo ""

cat << 'EOF'
gcloud functions deploy gcs_to_social \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=gcs_to_social \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=news-videos-1762459809" \
  --memory=512MB \
  --timeout=540s \
  --set-env-vars=GCP_PROJECT=news-automation-477419
EOF

echo ""
echo ""
echo "======================================"
echo "STEP 2: Grant Secret Manager Access"
echo "======================================"
echo ""
echo "After deployment completes (3-5 minutes), run these commands:"
echo ""

cat << 'EOF'
SA=$(gcloud functions describe gcs_to_social --region=us-central1 --gen2 --format='value(serviceConfig.serviceAccountEmail)')

gcloud projects add-iam-policy-binding news-automation-477419 \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"
EOF

echo ""
echo ""
echo "======================================"
echo "STEP 3: Test the Function"
echo "======================================"
echo ""
echo "Upload a test video to trigger the function:"
echo ""

cat << 'EOF'
# Create a simple test video file (or use an existing one)
# Then upload it:
gsutil cp your-test-video.mp4 gs://news-videos-1762459809/incoming/
EOF

echo ""
echo ""
echo "======================================"
echo "STEP 4: View Logs"
echo "======================================"
echo ""
echo "Check the function logs:"
echo ""

cat << 'EOF'
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50
EOF

echo ""
echo ""
echo "======================================"
echo "Ready to Deploy!"
echo "======================================"
echo ""
echo "Make sure you're in the ~/cloud-function directory in Cloud Shell, then run STEP 1 above."
echo ""
