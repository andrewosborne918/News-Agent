#!/bin/bash
# Deploy Cloud Function to Google Cloud Platform
# Run this script in Google Cloud Shell

set -e

echo "============================================================"
echo "Deploying Cloud Function to GCP"
echo "============================================================"

# Configuration
PROJECT_ID="news-automation-477419"
BUCKET="news-videos-1762459809"
REGION="us-central1"

echo ""
echo "Project: $PROJECT_ID"
echo "Bucket: $BUCKET"
echo "Region: $REGION"
echo ""

# Create function directory
echo "Creating function directory..."
mkdir -p ~/cloud-function
cd ~/cloud-function

# Create requirements.txt
echo "Creating requirements.txt..."
cat > requirements.txt << 'EOF'
google-api-python-client>=2.100.0
google-auth>=2.23.0
google-auth-httplib2>=0.1.1
google-auth-oauthlib>=1.1.0
google-cloud-storage>=2.10.0
google-cloud-secret-manager>=2.16.0
requests>=2.31.0
EOF

# Create main.py (Cloud Function code is in the uploader/main.py in your repo)
# We'll upload it separately

echo ""
echo "✅ Function files ready"
echo ""
echo "============================================================"
echo "Next: Upload main.py from your local repo to Cloud Shell"
echo "============================================================"
echo ""
echo "Instructions:"
echo "1. In Cloud Shell, click the ⋮ menu (top right)"
echo "2. Select 'Upload file'"
echo "3. Upload the file: uploader/main.py from your computer"
echo "4. Move it: mv ~/main.py ~/cloud-function/main.py"
echo "5. Then run: ./deploy_function.sh deploy"
echo ""
