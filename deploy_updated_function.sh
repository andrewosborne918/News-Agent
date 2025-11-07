#!/bin/bash

# Deploy the updated Cloud Function with improved error handling
# Run this from Google Cloud Shell

set -e

echo "======================================"
echo "Deploying Updated gcs-to-social Function"
echo "======================================"

cd uploader

echo ""
echo "Deploying with improved error handling for:"
echo "  ✓ YouTube upload limit exceeded"
echo "  ✓ Facebook token validation"
echo "  ✓ Graceful degradation (continues to FB if YT fails)"
echo ""

gcloud functions deploy gcs-to-social \
  --gen2 \
  --region=us-central1 \
  --runtime=python311 \
  --source=. \
  --entry-point=gcs_to_social \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=news-videos-1762459809" \
  --timeout=540s \
  --memory=1GiB

echo ""
echo "======================================"
echo "✅ Deployment Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "1. FIX YOUTUBE UPLOAD LIMITS:"
echo "   - Go to https://studio.youtube.com"
echo "   - Settings → Channel → Feature eligibility"
echo "   - Click 'Verify' and complete phone verification"
echo "   - See FIX_YOUTUBE_LIMITS.md for details"
echo ""
echo "2. FIX FACEBOOK TOKEN:"
echo "   - Generate a new Page Access Token"
echo "   - Update FB_PAGE_TOKEN secret:"
echo "     echo -n 'YOUR_NEW_TOKEN' | gcloud secrets versions add FB_PAGE_TOKEN --data-file=-"
echo "   - See FIX_FACEBOOK_TOKEN.md for step-by-step guide"
echo ""
echo "3. TEST THE FUNCTION:"
echo "   - Upload a test video to trigger the function"
echo "   - Check logs:"
echo "     gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50"
echo ""
