# Google Cloud Platform Free-Tier Automation Setup

🎯 **Goal**: Fully automated video posting to YouTube Shorts + Facebook using GCP's free tier

💰 **Cost**: $0/month (stays within GCP free tier)

⏱️ **Setup Time**: 45-60 minutes (one-time)

---

## Architecture Overview

```
GitHub Actions (generates video)
    ↓
Uploads to Google Cloud Storage
    ↓
Cloud Function triggers automatically
    ↓
Posts to YouTube Shorts + Facebook Page
    ↓
100% automated, 0% cost ✅
```

**Why This Works:**
- ✅ Official OAuth APIs (no bot detection)
- ✅ GCP free tier (generous limits)
- ✅ Fully serverless (no servers to maintain)
- ✅ Scales automatically
- ✅ Enterprise-grade reliability

---

## Prerequisites

- ✅ GitHub repository (you have this)
- ✅ Google account
- ✅ Facebook Page
- ✅ YouTube channel

---

## Part 1: Google Cloud Platform Setup

### Step 1: Create GCP Project

1. Go to: https://console.cloud.google.com/
2. Click "Select a project" → "New Project"
3. Project name: `news-automation`
4. Click "Create"
5. **Enable billing** (required for free tier)
   - Go to Billing
   - Link a payment method (won't be charged on free tier)

### Step 2: Enable Required APIs

Open Cloud Shell (terminal icon in top-right) and run:

```bash
# Set your project
gcloud config set project news-automation

# Enable services
gcloud services enable \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  youtube.googleapis.com
```

Also manually enable:
- Go to: APIs & Services → Library
- Search: "YouTube Data API v3"
- Click "Enable"

### Step 3: Create Storage Bucket

```bash
# Create unique bucket name
export BUCKET=news-videos-$RANDOM
gsutil mb -l us-central1 gs://$BUCKET
echo "Your bucket: $BUCKET"
# SAVE THIS BUCKET NAME - you'll need it later!
```

### Step 4: Create Service Account for GitHub

```bash
# Create service account
gcloud iam service-accounts create gh-actions-uploader \
  --display-name="GitHub Actions Uploader"

# Grant storage permissions
gcloud projects add-iam-policy-binding news-automation \
  --member="serviceAccount:gh-actions-uploader@news-automation.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"

# Create JSON key
gcloud iam service-accounts keys create gh-actions.json \
  --iam-account=gh-actions-uploader@news-automation.iam.gserviceaccount.com

# Display the JSON
cat gh-actions.json
```

**Copy the entire JSON output** - you'll add this to GitHub secrets.

---

## Part 2: YouTube OAuth Setup

### Step 1: Create OAuth Credentials

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure consent screen:
   - User type: External
   - App name: "News Automation"
   - Your email
   - Save
4. Application type: **Desktop app**
5. Name: "YouTube Uploader"
6. Click "Create"
7. **Copy Client ID and Client Secret**

### Step 2: Get Refresh Token (One-Time)

Create this file locally on your computer:

```python
# save as get_youtube_token.py
import google_auth_oauthlib.flow

CLIENT_ID     = "YOUR_CLIENT_ID_HERE"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"

flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(
    {"installed":{
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"
    }},
    scopes=["https://www.googleapis.com/auth/youtube.upload"]
)

creds = flow.run_local_server(port=0)
print("\n" + "="*60)
print("REFRESH TOKEN (save this!):")
print("="*60)
print(creds.refresh_token)
print("="*60)
```

Run it:
```bash
pip install google-auth-oauthlib
python get_youtube_token.py
```

- Browser will open
- Sign in to the Google account that owns your YouTube channel
- Authorize the app
- **Copy the REFRESH_TOKEN** that prints

---

## Part 3: Facebook Page Token

### Step 1: Create Facebook App

1. Go to: https://developers.facebook.com/apps/
2. Click "Create App"
3. Type: Business
4. App name: "News Automation"
5. Create app

### Step 2: Get Page Access Token

1. In your app, add "Facebook Login" product
2. Go to Graph API Explorer: https://developers.facebook.com/tools/explorer/
3. Select your app from dropdown
4. Click "Generate Access Token"
5. Grant permissions:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `pages_show_list`
   - `publish_video`
6. Authorize
7. **Copy the short-lived token**

### Step 3: Exchange for Long-Lived Token

In terminal:
```bash
curl -i -X GET "https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

**Copy the long-lived access_token** from response.

### Step 4: Get Page ID

1. Go to your Facebook Page
2. Settings → Page Info
3. Copy the "Page ID" number

---

## Part 4: Store Secrets in GCP

In Cloud Shell:

```bash
# YouTube secrets
echo -n "YOUR_CLIENT_ID" | gcloud secrets create YT_CLIENT_ID --data-file=-
echo -n "YOUR_CLIENT_SECRET" | gcloud secrets create YT_CLIENT_SECRET --data-file=-
echo -n "YOUR_REFRESH_TOKEN" | gcloud secrets create YT_REFRESH_TOKEN --data-file=-

# Facebook secrets
echo -n "YOUR_PAGE_ID" | gcloud secrets create FB_PAGE_ID --data-file=-
echo -n "YOUR_LONG_LIVED_TOKEN" | gcloud secrets create FB_PAGE_TOKEN --data-file=-

# Verify
gcloud secrets list
```

---

## Part 5: Create Cloud Function

### Step 1: Create Function Files

Create folder structure locally:
```
uploader/
  main.py
  requirements.txt
```

I'll create these files for you in the next step.

### Step 2: Deploy Cloud Function

```bash
cd uploader/
gcloud functions deploy gcs_to_social \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=YOUR_BUCKET_NAME" \
  --entry-point=gcs_to_social \
  --memory=512MB \
  --timeout=540s \
  --set-env-vars=GCP_PROJECT=news-automation
```

### Step 3: Grant Secret Access

```bash
# Get function's service account
SA=$(gcloud functions describe gcs_to_social --region=us-central1 --gen2 --format='value(serviceConfig.serviceAccountEmail)')

# Grant secret access
gcloud projects add-iam-policy-binding news-automation \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"
```

---

## Part 6: Update GitHub Workflow

Add these secrets to GitHub (Settings → Secrets → Actions):

- `GCP_SA_KEY`: The JSON from gh-actions.json
- `GCP_PROJECT_ID`: `news-automation`
- `GCS_BUCKET`: Your bucket name from Step 3

---

## Testing

### Test 1: Manual Upload

```bash
# Upload a test video
gsutil cp test-video.mp4 gs://YOUR_BUCKET/incoming/test.mp4

# Check Cloud Function logs
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50
```

You should see YouTube and Facebook video IDs in the logs!

### Test 2: GitHub Actions

Push your updated workflow and run it. The video will automatically post!

---

## Free Tier Limits

| Service | Free Tier | Your Usage | Safe? |
|---------|-----------|------------|-------|
| Cloud Storage | 5 GB | ~500 MB/month | ✅ |
| Cloud Functions | 2M invocations | 150/month | ✅ |
| Cloud Build | 120 min/day | ~30 min/day | ✅ |
| Secret Manager | 6 active secrets | 5 secrets | ✅ |
| YouTube API | 10,000 units/day | 1,600/day | ✅ |

**Your usage stays well within free tier! 🎉**

---

## Adding TikTok Later

1. Apply for TikTok Content Posting API
2. Get access token
3. Add `_upload_tiktok()` function to main.py
4. Redeploy Cloud Function

---

## Maintenance

### View Logs
```bash
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50
```

### Check Storage Usage
```bash
gsutil du -sh gs://YOUR_BUCKET
```

### Rotate Facebook Token (every 60 days)
Re-run the token exchange in Part 3, Step 3.

---

## Troubleshooting

### Function fails with "403 Forbidden"
- Check service account has `secretmanager.secretAccessor` role
- Verify secrets exist: `gcloud secrets list`

### YouTube upload fails
- Verify channel is verified (required for uploads)
- Check quota: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas

### Facebook upload fails
- Token might be expired - regenerate long-lived token
- Check page permissions in Facebook app

---

## Next Steps

I'll create:
1. The Cloud Function files (main.py, requirements.txt)
2. Updated GitHub Actions workflow
3. A testing script

Ready to proceed? 🚀
