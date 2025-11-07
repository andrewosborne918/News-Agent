# Error Fix Summary - YouTube & Facebook Upload Issues

## Overview

Your Cloud Function is encountering two separate errors:

1. **YouTube**: Upload limit exceeded (channel not verified)
2. **Facebook**: Invalid access token (token expired/invalidated)

## ✅ What I Fixed

### 1. Improved Error Handling in `uploader/main.py`

#### YouTube Upload Handling
- ✅ Added proper exception handling for `HttpError` and `ResumableUploadError`
- ✅ Specific detection of `uploadLimitExceeded` errors
- ✅ Clear, actionable error messages with steps to fix
- ✅ Graceful continuation to Facebook even if YouTube fails

#### Facebook Token Validation
- ✅ Enhanced preflight check that validates token before upload
- ✅ Clear error messages when token is invalid
- ✅ Step-by-step instructions in error output
- ✅ Better error logging with error details

#### Status Tracking
- ✅ Tracks success/failure per platform independently
- ✅ Returns detailed status: `success`, `partial_success`, or `failed`
- ✅ JSON output shows which platforms succeeded

### 2. Created Detailed Fix Guides

Created two comprehensive guides:
- **FIX_YOUTUBE_LIMITS.md** - How to verify your channel and handle upload limits
- **FIX_FACEBOOK_TOKEN.md** - Step-by-step token regeneration guide

### 3. Deployment Script

Created `deploy_updated_function.sh` - One command to deploy all fixes

## 🚨 Immediate Actions Required

### Action 1: Verify Your YouTube Channel (5 minutes)

This solves the upload limit issue:

1. Go to https://studio.youtube.com
2. Click Settings → Channel → Feature eligibility
3. Find "Intermediate features" or "Advanced features"
4. Click **"Verify"** next to phone verification
5. Enter your phone number and verification code
6. **Wait 10-15 minutes** after verification

**Why**: Unverified channels can only upload 6 videos per 24 hours. Verified channels have no daily limit.

### Action 2: Regenerate Facebook Page Token (10 minutes)

Your current token is invalid. Follow these steps:

#### Quick Steps:
```bash
# 1. Get long-lived user token (go to Graph API Explorer first)
# Select your app, request permissions: pages_show_list, pages_manage_posts, 
# pages_read_engagement, pages_manage_metadata, publish_video

# 2. Exchange for long-lived token
curl -G "https://graph.facebook.com/v19.0/oauth/access_token" \
  -d "grant_type=fb_exchange_token" \
  -d "client_id=YOUR_APP_ID" \
  -d "client_secret=YOUR_APP_SECRET" \
  -d "fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"

# 3. Get Page token from /me/accounts
curl "https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_LONG_LIVED_USER_TOKEN"

# 4. Copy the "access_token" field for your page (this is your PAGE token)

# 5. Update the secret in Cloud Shell
echo -n "YOUR_PAGE_TOKEN" | gcloud secrets versions add FB_PAGE_TOKEN --data-file=-
```

**Full details**: See `FIX_FACEBOOK_TOKEN.md`

### Action 3: Deploy Updated Code

Run from **Google Cloud Shell** (not local terminal):

```bash
cd ~/News-Agent
./deploy_updated_function.sh
```

Or manually:
```bash
cd ~/News-Agent/uploader
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
```

## 📊 What Will Change

### Before (Current State):
```
Uploading to YouTube...
Exception: uploadLimitExceeded
❌ ERROR! (entire function fails)
```

### After (With Updates):
```
Uploading to YouTube: Your Video Title
⚠️ YouTube upload limit exceeded.
   Action needed:
   1. Verify your YouTube channel (phone verification in YouTube Studio)
   2. Wait 24 hours before uploading more videos
   3. Consider rate-limiting uploads to avoid hitting this limit
   Continuing with Facebook upload...

Facebook token preflight...
FB token valid: True | Granted perms: ['pages_manage_posts', ...]
Waiting 23 seconds before Facebook upload...
------------------------------------------------------------
Uploading to Facebook
✅ Facebook upload complete: Video ID 123456789

⚠️ PARTIAL SUCCESS (at least one platform succeeded)
{
  "status": "partial_success",
  "youtube_success": false,
  "facebook_success": true,
  "facebook_video_id": "123456789",
  "source_file": "incoming/news_video_1762545174.mp4"
}
```

## 🔍 Testing After Deployment

### 1. Check Logs
```bash
gcloud functions logs read gcs_to_social \
  --region=us-central1 \
  --gen2 \
  --limit=50
```

### 2. Trigger a Test Upload
Upload a test video to GCS:
```bash
gsutil cp test_video.mp4 gs://news-videos-1762459809/incoming/
```

### 3. Verify Success Messages
Look for:
- `✅ YouTube upload complete:` (after channel verification)
- `✅ Facebook upload complete:` (after token update)
- `⚠️ PARTIAL SUCCESS` or `✅ COMPLETE SUCCESS!`

## 📈 Long-term Improvements (Optional)

### 1. Rate Limiting
Modify your video generation workflow to create videos less frequently:
- Current: Every hour (24 videos/day)
- Recommended: Every 2-3 hours (8-12 videos/day)

### 2. Upload Queue
Implement a retry queue for failed uploads (see `FIX_YOUTUBE_LIMITS.md`)

### 3. System User Token for Facebook
Use a permanent System User token instead of user tokens (see `FIX_FACEBOOK_TOKEN.md`)

### 4. Monitoring Dashboard
Set up alerts for:
- Upload failures
- Token expiration warnings
- Daily upload counts

## 📝 Files Changed/Created

### Modified:
- `uploader/main.py` - Enhanced error handling

### Created:
- `FIX_YOUTUBE_LIMITS.md` - YouTube verification guide
- `FIX_FACEBOOK_TOKEN.md` - Facebook token regeneration guide  
- `deploy_updated_function.sh` - Deployment script
- `ERROR_FIX_SUMMARY.md` - This file

## 🎯 Expected Timeline

| Task | Time | Priority |
|------|------|----------|
| Verify YouTube channel | 5 min | ⭐⭐⭐ Critical |
| Regenerate FB token | 10 min | ⭐⭐⭐ Critical |
| Deploy updated code | 5 min | ⭐⭐⭐ Critical |
| Test uploads | 10 min | ⭐⭐ Important |
| Set up rate limiting | 30 min | ⭐ Optional |

**Total time to fix critical issues: ~20 minutes**

## ❓ Troubleshooting

### "gcloud command not found" locally
- ✅ Deploy from Google Cloud Shell instead
- Cloud Shell has gcloud pre-installed

### YouTube still showing upload limit after verification
- Wait 10-15 minutes after verification
- Clear browser cache and check YouTube Studio again
- Verify you verified the correct channel

### Facebook token still failing
- Make sure you're using the PAGE token, not USER token
- Check token with debug endpoint:
  ```bash
  curl "https://graph.facebook.com/debug_token?input_token=YOUR_TOKEN&access_token=YOUR_APP_ID|YOUR_APP_SECRET"
  ```

### Both platforms still failing
- Check Cloud Function logs for specific errors
- Verify secrets are correctly set in Secret Manager:
  ```bash
  gcloud secrets versions access latest --secret="YT_REFRESH_TOKEN"
  gcloud secrets versions access latest --secret="FB_PAGE_TOKEN"
  ```

## 📞 Support

If you need help:
1. Check the detailed guides: `FIX_YOUTUBE_LIMITS.md` and `FIX_FACEBOOK_TOKEN.md`
2. Review Cloud Function logs for specific error messages
3. Check that all secrets are properly configured in Secret Manager

## ✨ Summary

**The code is now fixed** to handle errors gracefully. However, you still need to:
1. ✅ Verify your YouTube channel (removes upload limit)
2. ✅ Generate new Facebook Page token (fixes authentication)
3. ✅ Deploy the updated code

Once these three steps are complete, your automated video posting will work reliably! 🚀
